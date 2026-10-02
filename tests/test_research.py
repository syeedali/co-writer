import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cowriter.research import (  # noqa: E402
    ClaimQuery,
    EvidenceSource,
    ResearchError,
    build_claim_extraction_prompt,
    classify_evidence_design,
    format_evidence,
    format_source_record,
    parse_claim_queries,
    search_europe_pmc,
)


class ResearchTests(unittest.TestCase):
    def test_extraction_prompt_protects_lived_experience(self):
        prompt = build_claim_extraction_prompt("I remember what happened.")

        self.assertIn("Do not reinterpret lived experience as a diagnosis", prompt)
        self.assertIn("I remember what happened.", prompt)

    def test_parse_claim_queries_accepts_fenced_json(self):
        response = '''```json
{"claims":[{"claim":"Play supports language development.","query":"play language development children"}]}
```'''

        self.assertEqual(
            parse_claim_queries(response),
            [
                ClaimQuery(
                    claim="Play supports language development.",
                    query="play language development children",
                )
            ],
        )

    def test_parse_claim_queries_rejects_missing_claims(self):
        with self.assertRaises(ResearchError):
            parse_claim_queries('{"claims": []}')

    def test_parse_claim_queries_keeps_lived_experience_local(self):
        response = '{"claims":[{"claim":"I felt afraid.","kind":"lived_experience","query":""}]}'

        self.assertEqual(
            parse_claim_queries(response),
            [ClaimQuery(claim="I felt afraid.", query="", kind="lived_experience")],
        )

    def test_classify_evidence_design_flags_synthesis_and_preprints(self):
        self.assertEqual(
            classify_evidence_design(("Systematic Review", "Meta-Analysis")),
            "Evidence synthesis (systematic review/meta-analysis)",
        )
        self.assertEqual(
            classify_evidence_design(("Research Article",), is_preprint=True),
            "Preprint (not necessarily peer reviewed)",
        )

    def test_search_europe_pmc_maps_metadata(self):
        response = Mock()
        response.json.return_value = {
            "resultList": {
                "result": [
                    {
                        "title": "A study",
                        "authorString": "Researcher A",
                        "pubYear": "2025",
                        "journalTitle": "Development",
                        "abstractText": "Evidence from the study.",
                        "doi": "10.1234/example",
                        "pubTypeList": {"pubType": ["Systematic Review"]},
                        "citedByCount": 14,
                    }
                ]
            }
        }
        http = Mock()
        http.get.return_value = response

        sources = search_europe_pmc("child development", http=http)

        response.raise_for_status.assert_called_once_with()
        self.assertEqual(sources[0].title, "A study")
        self.assertEqual(sources[0].url, "https://doi.org/10.1234/example")
        self.assertEqual(sources[0].citation_count, 14)
        self.assertEqual(
            sources[0].evidence_design,
            "Evidence synthesis (systematic review/meta-analysis)",
        )
        self.assertEqual(http.get.call_args.kwargs["params"]["resultType"], "core")

    def test_search_europe_pmc_retries_transient_errors(self):
        timeout = requests.Timeout("temporary timeout")
        response = Mock()
        response.json.return_value = {"resultList": {"result": []}}
        http = Mock()
        http.get.side_effect = [timeout, response]

        with patch("cowriter.research.sleep"):
            self.assertEqual(search_europe_pmc("child development", http=http), [])

        self.assertEqual(http.get.call_count, 2)

    def test_format_evidence_numbers_sources(self):
        claim = ClaimQuery("A claim", "a query")
        source = EvidenceSource(
            title="A study",
            authors="Researcher A",
            year="2025",
            journal="Development",
            abstract="Evidence.",
            url="https://doi.org/10.1234/example",
        )

        evidence = format_evidence([(claim, [source])])

        self.assertIn("CLAIM 1: A claim", evidence)
        self.assertIn("[1] Researcher A (2025). A study.", evidence)
        self.assertIn("URL: https://doi.org/10.1234/example", evidence)

    def test_source_record_preserves_claim_to_link_mapping(self):
        claim = ClaimQuery("A claim", "a query")
        source = EvidenceSource(
            title="A study",
            authors="Researcher A",
            year="2025",
            journal="Development",
            abstract="Evidence.",
            url="https://doi.org/10.1234/example",
        )

        record = format_source_record([(claim, [source])])

        self.assertIn("### Claim 1: A claim", record)
        self.assertIn("[1] [A study](https://doi.org/10.1234/example)", record)


if __name__ == "__main__":
    unittest.main()
