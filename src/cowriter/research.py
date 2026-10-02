"""Scholarly evidence lookup helpers for Co-Writer's fact checker."""

import json
from dataclasses import dataclass
from time import sleep

import requests


EUROPE_PMC_SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
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


def build_claim_extraction_prompt(passage):
    """Build the local-only prompt that separates testimony from checkable claims."""
    return f"""Classify up to five important statements in this passage as one of:
- lived_experience: first-person events, feelings, or observations
- research_claim: general factual claims about people, development, trauma, or outcomes
- clinical_interpretation: diagnostic language or an inference about a specific person's condition
- legal_claim: statements about laws, rights, custody, reporting, or legal standards

Do not reinterpret lived experience as a diagnosis. For each research_claim or clinical_interpretation, write a neutral scholarly search query of at most 12 words. Other classifications must use an empty query.
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
            claims.append(ClaimQuery(claim=claim, query=query[:200], kind=kind))
        if len(claims) >= limit:
            break

    if not claims:
        raise ResearchError("No checkable factual claims were found.")
    return claims


def search_europe_pmc(query, limit=4, http=requests):
    """Return relevant scholarly sources from the public Europe PMC API."""
    params = {
        "query": query,
        "format": "json",
        "resultType": "core",
        "pageSize": limit,
    }
    for attempt in range(2):
        try:
            response = http.get(
                EUROPE_PMC_SEARCH_URL,
                params=params,
                headers={"User-Agent": "Co-Writer/4.0 research companion"},
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
            results = payload.get("resultList", {}).get("result", []) if isinstance(payload, dict) else []
            break
        except (requests.RequestException, ValueError, TypeError, AttributeError) as exc:
            if attempt == 0 and _is_transient_error(exc):
                sleep(0.5)
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

        pub_type_value = result.get("pubTypeList", {}).get("pubType", [])
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
            )
        )
    return sources


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


def format_evidence(claim_sources):
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
        if claim_query.kind == "lived_experience":
            lines.append("No external verification requested: this is the writer's lived experience.")
        elif claim_query.kind == "legal_claim":
            lines.append("Not searched in Europe PMC: legal claims require current jurisdiction-specific sources.")
        elif not sources:
            lines.append("No relevant scholarly sources were found.")
        for source in sources:
            citation = f"[{source_number}] {source.authors} ({source.year}). {source.title}."
            if source.journal:
                citation += f" {source.journal}."
            lines.extend(
                [
                    citation,
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


def format_source_record(claim_sources):
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
        if not sources:
            lines.append("- Retrieved sources: none")
        for source in sources:
            lines.extend(
                [
                    f"- [{source_number}] [{source.title}]({source.url})",
                    f"  - {source.authors} ({source.year}); {source.journal or 'Journal not supplied'}",
                    f"  - Design context: {source.evidence_design}",
                    f"  - Cited by: {source.citation_count} (not a quality score)",
                ]
            )
            source_number += 1
        sections.append("\n".join(lines))
    return "\n\n".join(sections)
