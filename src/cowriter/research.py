"""Scholarly evidence lookup helpers for Co-Writer's fact checker."""

import json
import re
import threading
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from time import monotonic, sleep
from urllib.parse import unquote, urlparse

import requests
from .jobs import JobCancelled


EUROPE_PMC_SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
ARXIV_SEARCH_URL = "https://export.arxiv.org/api/query"
OPENALEX_SEARCH_URL = "https://api.openalex.org/works"
EVIDENCE_PROVIDERS = {
    "europe_pmc": ("Europe PMC", "Biomedical and life science literature"),
    "arxiv": ("arXiv", "Physics, mathematics, computing and other preprints"),
    "openalex": ("OpenAlex", "Scholarly publications across disciplines"),
}
_arxiv_lock = threading.Lock()
_arxiv_last_request = 0.0
CLAIM_KINDS = {
    "lived_experience",
    "research_claim",
    "clinical_interpretation",
    "legal_claim",
}


class ResearchError(RuntimeError):
    """Raised when claims cannot be parsed or evidence cannot be retrieved."""


@dataclass(frozen=True)
class ClaimQuery:
    claim: str
    query: str
    kind: str = "research_claim"


@dataclass(frozen=True)
class EvidenceSource:
    title: str
    authors: str
    year: str
    journal: str
    abstract: str
    url: str
    publication_types: tuple = ()
    evidence_design: str = "Unclassified publication"
    citation_count: int = 0
    is_preprint: bool = False
    doi: str = ""
    arxiv_id: str = ""
    providers: tuple = ()
    is_retracted: bool = False


@dataclass(frozen=True)
class EvidenceSearch:
    sources: list
    coverage: tuple


def build_claim_extraction_prompt(passage):
    """Build the local-only prompt that separates testimony from checkable claims."""
    return f"""Classify up to five important statements in this passage as one of:
- lived_experience: first-person events, feelings, or observations
- research_claim: general factual claims in any field, including science, technology, history, people, or outcomes
- clinical_interpretation: diagnostic language or an inference about a specific person's condition
- legal_claim: statements about laws, rights, custody, reporting, or legal standards

Do not reinterpret lived experience as a diagnosis. For each research_claim or clinical_interpretation, write a neutral scholarly search query of at most 12 words. Omit personal names, contact details and identifying details from queries. Other classifications must use an empty query.
Return JSON only in this exact shape:
{{"claims":[{{"claim":"claim text","kind":"research_claim","query":"scholarly search terms"}}]}}
Do not assess the claims yet.

PASSAGE:
{passage}"""


def classify_evidence_design(publication_types, is_preprint=False):
    """Describe study design without pretending that design alone proves quality."""
    joined = " ".join(publication_types).lower()
    if is_preprint or "preprint" in joined:
        return "Preprint (not necessarily peer reviewed)"
    if "meta-analysis" in joined or "systematic review" in joined:
        return "Evidence synthesis (systematic review/meta-analysis)"
    if "practice guideline" in joined or "guideline" in joined:
        return "Clinical or practice guideline"
    if "randomized controlled trial" in joined or "controlled clinical trial" in joined:
        return "Controlled intervention study"
    if "review" in joined:
        return "Narrative or unspecified review"
    if any(term in joined for term in ("cohort", "longitudinal", "observational")):
        return "Observational or longitudinal study"
    return "Primary or other publication"


def parse_claim_queries(response_text, limit=5):
    """Parse the small JSON object requested from the local model."""
    start = response_text.find("{")
    end = response_text.rfind("}")
    if start < 0 or end <= start:
        raise ResearchError("The model did not return a claim list.")

    try:
        payload = json.loads(response_text[start:end + 1])
        items = payload.get("claims", []) if isinstance(payload, dict) else []
    except json.JSONDecodeError as exc:
        raise ResearchError("The model returned an invalid claim list.") from exc

    claims = []
    for item in items:
        if not isinstance(item, dict):
            continue
        claim = str(item.get("claim", "")).strip()
        query = " ".join(str(item.get("query", "")).split()).strip()
        kind = str(item.get("kind", "research_claim")).strip().lower()
        if kind not in CLAIM_KINDS:
            kind = "research_claim"
        needs_literature = kind in {"research_claim", "clinical_interpretation"}
        if claim and (query or not needs_literature):
            # Search terms are the only draft-derived content sent externally.
            claims.append(ClaimQuery(claim=claim, query=" ".join(query.split()[:12])[:200] if needs_literature else "", kind=kind))
        if len(claims) >= limit:
            break

    if not claims:
        raise ResearchError("No checkable factual claims were found.")
    return claims


def search_europe_pmc(query, limit=4, http=requests, cancel_event=None):
    """Return relevant scholarly sources from the public Europe PMC API."""
    params = {
        "query": query,
        "format": "json",
        "resultType": "core",
        "pageSize": limit,
    }
    for attempt in range(2):
        if cancel_event is not None and cancel_event.is_set():
            raise JobCancelled()
        try:
            response = http.get(
                EUROPE_PMC_SEARCH_URL,
                params=params,
                headers={"User-Agent": "Co-Writer/4.0 research companion"},
                timeout=20,
            )
            response.raise_for_status()
            if cancel_event is not None and cancel_event.is_set():
                raise JobCancelled()
            payload = response.json()
            results = payload.get("resultList", {}).get("result") if isinstance(payload, dict) else None
            if not isinstance(results, list):
                raise ValueError("Invalid result list")
            break
        except (requests.RequestException, ValueError, TypeError, AttributeError) as exc:
            if attempt == 0 and _is_transient_error(exc):
                if cancel_event is None:
                    sleep(0.5)
                elif cancel_event.wait(0.5):
                    raise JobCancelled()
                continue
            raise ResearchError(f"Europe PMC lookup failed: {exc}") from exc

    sources = []
    for result in results[:limit]:
        if not isinstance(result, dict):
            continue
        doi = result.get("doi")
        pmid = result.get("pmid")
        source = result.get("source")
        source_id = result.get("id")
        if doi:
            url = f"https://doi.org/{doi}"
        elif pmid:
            url = f"https://europepmc.org/article/MED/{pmid}"
        elif source and source_id:
            url = f"https://europepmc.org/article/{source}/{source_id}"
        else:
            url = "https://europepmc.org/"

        pub_types = result.get("pubTypeList")
        pub_type_value = pub_types.get("pubType", []) if isinstance(pub_types, dict) else []
        if isinstance(pub_type_value, str):
            publication_types = (pub_type_value,)
        elif isinstance(pub_type_value, list):
            publication_types = tuple(str(value) for value in pub_type_value)
        else:
            publication_types = ()
        is_preprint = str(source).upper() == "PPR" or any(
            "preprint" in value.lower() for value in publication_types
        )

        sources.append(
            EvidenceSource(
                title=str(result.get("title") or "Untitled source").strip(),
                authors=str(result.get("authorString") or "Unknown authors").strip(),
                year=str(result.get("pubYear") or "n.d.").strip(),
                journal=str(result.get("journalTitle") or "").strip(),
                abstract=" ".join(str(result.get("abstractText") or "").split())[:1800],
                url=url,
                publication_types=publication_types,
                evidence_design=classify_evidence_design(publication_types, is_preprint),
                citation_count=_safe_int(result.get("citedByCount")),
                is_preprint=is_preprint,
                doi=str(doi or ""),
                providers=("Europe PMC",),
                is_retracted=any("retract" in value.lower() for value in publication_types),
            )
        )
    return sources


def _check_cancel(cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise JobCancelled()


def _wait(seconds, cancel_event):
    _check_cancel(cancel_event)
    if cancel_event is None:
        sleep(seconds)
    elif cancel_event.wait(seconds):
        raise JobCancelled()


def _request(url, params, provider, http, cancel_event, parse, before_request=None):
    for attempt in range(2):
        _check_cancel(cancel_event)
        try:
            if before_request:
                before_request()
            response = http.get(url, params=params,
                                headers={"User-Agent": "Co-Writer/4.0 evidence checker"}, timeout=20)
            response.raise_for_status()
            _check_cancel(cancel_event)
            return parse(response)
        except (requests.RequestException, ValueError, TypeError, AttributeError, ET.ParseError) as exc:
            if attempt == 0 and _is_transient_error(exc):
                _wait(1, cancel_event)
                continue
            # Avoid exposing request URLs (which contain draft-derived queries).
            status = getattr(getattr(exc, "response", None), "status_code", None)
            detail = f"HTTP {status}" if status else "connection or response error"
            raise ResearchError(f"{provider} unavailable ({detail})") from exc


def search_arxiv(query, limit=4, http=requests, cancel_event=None):
    """Search Atom metadata, spacing requests and marking manuscripts as preprints."""
    terms = re.findall(r"[\w-]+", query, re.UNICODE)[:12]
    if not terms:
        return []
    params = {"search_query": " AND ".join(f'all:"{term}"' for term in terms),
              "start": 0, "max_results": limit, "sortBy": "relevance", "sortOrder": "descending"}
    # arXiv requires one connection at a time and at least three seconds
    # between requests, including retries and successive evidence checks.
    while not _arxiv_lock.acquire(timeout=0.1):
        _check_cancel(cancel_event)
    try:
        def pace():
            global _arxiv_last_request
            delay = max(0, 3 - (monotonic() - _arxiv_last_request))
            _wait(delay, cancel_event)
            _arxiv_last_request = monotonic()
        root = _request(ARXIV_SEARCH_URL, params, "arXiv", http, cancel_event,
                        lambda response: ET.fromstring(response.text), pace)
    finally:
        _arxiv_lock.release()
    ns = {"a": "http://www.w3.org/2005/Atom", "ar": "http://arxiv.org/schemas/atom"}
    if root.tag != "{http://www.w3.org/2005/Atom}feed":
        raise ResearchError("arXiv returned an invalid feed")
    sources = []
    for entry in root.findall("a:entry", ns)[:limit]:
        identifier = entry.findtext("a:id", "", ns)
        if "api/errors" in identifier:
            raise ResearchError("arXiv returned a search error")
        arxiv_id = re.sub(r"v\d+$", "", identifier.split("/abs/")[-1])
        if not identifier or not arxiv_id:
            continue
        sources.append(EvidenceSource(
            title=" ".join(entry.findtext("a:title", "Untitled source", ns).split()),
            authors=", ".join(author.findtext("a:name", "", ns) for author in entry.findall("a:author", ns)),
            year=entry.findtext("a:published", "n.d.", ns)[:4],
            journal=entry.findtext("ar:journal_ref", "", ns),
            abstract=" ".join(entry.findtext("a:summary", "", ns).split())[:1800],
            url=f"https://arxiv.org/abs/{arxiv_id}", doi=entry.findtext("ar:doi", "", ns),
            arxiv_id=arxiv_id, providers=("arXiv",), publication_types=("Preprint",),
            is_preprint=True, evidence_design=classify_evidence_design((), True),
        ))
    return sources


def _openalex_abstract(index):
    if not isinstance(index, dict):
        return ""
    words = {}
    for word, positions in index.items():
        if isinstance(positions, list):
            for position in positions:
                if isinstance(position, int) and 0 <= position < 5000:
                    words[position] = str(word)
    return " ".join(words[position] for position in sorted(words))[:1800]


def search_openalex(query, limit=4, http=requests, cancel_event=None):
    """Use OpenAlex's keyless basic search and reconstruct available abstracts."""
    payload = _request(OPENALEX_SEARCH_URL, {"search": query, "per_page": limit},
                       "OpenAlex", http, cancel_event, lambda response: response.json())
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ResearchError("OpenAlex returned an invalid result list")
    sources = []
    for work in payload["results"][:limit]:
        if not isinstance(work, dict):
            continue
        location = work.get("primary_location") or {}
        venue = location.get("source") or {}
        doi = str(work.get("doi") or "")
        url = doi or location.get("landing_page_url") or work.get("id")
        if not url:
            continue
        preprint = work.get("type") == "preprint" or location.get("version") == "submittedVersion"
        publication_types = (str(work.get("type") or "Unclassified publication"),)
        authors = work.get("authorships") or []
        arxiv_id = ""
        for work_location in work.get("locations") or [location]:
            landing = str(work_location.get("landing_page_url") or "")
            if urlparse(landing).hostname in {"arxiv.org", "export.arxiv.org"} and "/abs/" in landing:
                arxiv_id = re.sub(r"v\d+$", "", urlparse(landing).path.split("/abs/")[-1])
                break
        sources.append(EvidenceSource(
            title=str(work.get("display_name") or "Untitled source"),
            authors=", ".join(str((entry.get("author") or {}).get("display_name") or "Unknown author")
                              for entry in authors if isinstance(entry, dict)) or "Unknown authors",
            year=str(work.get("publication_year") or "n.d."),
            journal=str(venue.get("display_name") or ""),
            abstract=_openalex_abstract(work.get("abstract_inverted_index")), url=str(url), doi=doi,
            providers=("OpenAlex",), arxiv_id=arxiv_id, publication_types=publication_types, is_preprint=preprint,
            is_retracted=bool(work.get("is_retracted")),
            citation_count=_safe_int(work.get("cited_by_count")),
            evidence_design=classify_evidence_design(publication_types, preprint),
        ))
    return sources


def _normalized_doi(value):
    return re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", unquote(value).strip(), flags=re.I).lower()


def deduplicate_sources(sources):
    """Merge copies of a publication; preserve different works with the same title."""
    def identity(source):
        doi = _normalized_doi(source.doi or (source.url if "doi.org/" in source.url else ""))
        arxiv_id = source.arxiv_id
        if not arxiv_id and urlparse(source.url).hostname in {"arxiv.org", "export.arxiv.org"}:
            arxiv_id = urlparse(source.url).path.split("/abs/")[-1]
        return doi, re.sub(r"v\d+$", "", arxiv_id), re.sub(r"\W+", "", source.title.casefold())

    def same_work(first, second):
        doi_a, arxiv_a, title_a = identity(first)
        doi_b, arxiv_b, title_b = identity(second)
        if (doi_a and doi_a == doi_b) or (arxiv_a and arxiv_a == arxiv_b):
            return True
        conflicting_ids = (doi_a and doi_b and doi_a != doi_b) or (arxiv_a and arxiv_b and arxiv_a != arxiv_b)
        return bool(not conflicting_ids and title_a and title_a == title_b
                    and first.title != "Untitled source" and first.year == second.year)

    def merge(first, second):
        preferred = second if first.is_preprint and not second.is_preprint else first
        return replace(preferred,
            providers=tuple(dict.fromkeys(first.providers + second.providers)),
            abstract=preferred.abstract or first.abstract or second.abstract,
            doi=preferred.doi or first.doi or second.doi,
            arxiv_id=first.arxiv_id or second.arxiv_id,
            citation_count=max(first.citation_count, second.citation_count),
            is_retracted=first.is_retracted or second.is_retracted)

    merged = []
    for source in sources:
        matches = [index for index, previous in enumerate(merged) if same_work(previous, source)]
        if not matches:
            merged.append(source)
            continue
        combined = merged[matches[0]]
        for index in matches[1:]:
            combined = merge(combined, merged[index])
        merged[matches[0]] = merge(combined, source)
        for index in reversed(matches[1:]):
            merged.pop(index)
    return merged


def search_evidence(query, providers=None, limit=4, http=requests, cancel_event=None, on_progress=None):
    """Search selected indexes; preserve partial results and a coverage record."""
    selected = tuple(EVIDENCE_PROVIDERS) if providers is None else tuple(providers)
    if not selected or any(provider not in EVIDENCE_PROVIDERS for provider in selected):
        raise ResearchError("Choose at least one available source collection")
    lookups = {"europe_pmc": search_europe_pmc, "arxiv": search_arxiv, "openalex": search_openalex}
    sources, coverage = [], []
    for provider in dict.fromkeys(selected):
        _check_cancel(cancel_event)
        label = EVIDENCE_PROVIDERS[provider][0]
        if on_progress:
            on_progress(label)
        try:
            results = lookups[provider](query, limit=limit, http=http, cancel_event=cancel_event)
        except (ResearchError, ValueError, TypeError, AttributeError):
            coverage.append(f"{label}: unavailable; this collection could not be checked.")
        else:
            sources.extend(results)
            coverage.append(f"{label}: {len(results)} publication(s) retrieved.")
    _check_cancel(cancel_event)
    return EvidenceSearch(deduplicate_sources(sources), tuple(coverage))


def _is_transient_error(exc):
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return True
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None) in {429, 500, 502, 503, 504}


def _safe_int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def format_evidence(claim_sources, coverage=()):
    """Format retrieved metadata for evidence-grounded local-LLM review."""
    sections = []
    source_number = 1
    for claim_number, (claim_query, sources) in enumerate(claim_sources, start=1):
        lines = [
            f"CLAIM {claim_number}: {claim_query.claim}",
            f"CLAIM TYPE: {claim_query.kind}",
        ]
        if claim_query.query:
            lines.append(f"SEARCH QUERY: {claim_query.query}")
        if claim_number <= len(coverage):
            lines.extend(f"SEARCH COVERAGE: {item}" for item in coverage[claim_number - 1])
        if claim_query.kind == "lived_experience":
            lines.append("No external verification requested: this is the writer's lived experience.")
        elif claim_query.kind == "legal_claim":
            lines.append("Not searched in scholarly indexes: legal claims require current jurisdiction-specific sources.")
        elif not sources:
            lines.append("No scholarly publications retrieved. Consult search coverage for failures; this does not disprove the claim.")
        for source in sources:
            citation = f"[{source_number}] {source.authors} ({source.year}). {source.title}."
            if source.journal:
                citation += f" {source.journal}."
            lines.extend(
                [
                    citation,
                    f"FOUND VIA: {', '.join(source.providers) or 'Not recorded'}",
                    f"PREPRINT: {'Yes; peer review not verified' if source.is_preprint else 'Not identified as a preprint; peer review not verified'}",
                    f"RETRACTED: {'Yes; do not treat as reliable support' if source.is_retracted else 'Not flagged by the source index'}",
                    f"EVIDENCE DESIGN: {source.evidence_design}",
                    f"PUBLICATION TYPES: {', '.join(source.publication_types) or 'Not supplied'}",
                    f"CITED BY: {source.citation_count} (context only; not a quality score)",
                    f"URL: {source.url}",
                    f"ABSTRACT: {source.abstract or '[No abstract available]'}",
                ]
            )
            source_number += 1
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


def format_source_record(claim_sources, coverage=()):
    """Create a compact, deterministic claim-to-source record for saved audits."""
    sections = []
    source_number = 1
    for claim_number, (claim_query, sources) in enumerate(claim_sources, start=1):
        lines = [
            f"### Claim {claim_number}: {claim_query.claim}",
            f"- Classification: `{claim_query.kind}`",
        ]
        if claim_query.query:
            lines.append(f"- Search query: `{claim_query.query}`")
        if claim_number <= len(coverage):
            lines.extend(f"- Search coverage: {item}" for item in coverage[claim_number - 1])
        if not sources:
            lines.append("- Retrieved sources: none")
        for source in sources:
            lines.extend(
                [
                    f"- [{source_number}] [{source.title}]({source.url})",
                    f"  - {source.authors} ({source.year}); {source.journal or 'Journal not supplied'}",
                    f"  - Design context: {source.evidence_design}",
                    f"  - Found via: {', '.join(source.providers) or 'Not recorded'}",
                    "  - Peer review: not independently verified",
                    f"  - Cited by: {source.citation_count} (not a quality score)",
                ]
            )
            if source.is_preprint:
                lines.append("  - Preprint/manuscript: peer review not verified")
            if source.is_retracted:
                lines.append("  - RETRACTED: do not treat as reliable support")
            source_number += 1
        sections.append("\n".join(lines))
    return "\n\n".join(sections)
