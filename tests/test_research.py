import sys
import json
import unittest
import threading
from pathlib import Path
from dataclasses import replace
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
    search_arxiv,
    search_openalex,
    search_evidence,
    deduplicate_sources,
)
from cowriter.jobs import JobCancelled


class ResearchTests(unittest.TestCase):
    def test_search_arxiv_maps_atom_and_labels_preprint(self):
        response = Mock(text='''<feed xmlns="http://www.w3.org/2005/Atom"
            xmlns:arxiv="http://arxiv.org/schemas/atom"><entry>
            <id>http://arxiv.org/abs/2501.01234v2</id><title> A\n paper </title>
            <published>2025-01-02T00:00:00Z</published><summary>Useful abstract.</summary>
            <author><name>Writer A</name></author><arxiv:doi>10.1234/test</arxiv:doi>
            <arxiv:journal_ref>Published journal reference</arxiv:journal_ref>
            </entry></feed>''')
        http = Mock()
        http.get.return_value = response
        with patch('cowriter.research._arxiv_last_request', 0):
            sources = search_arxiv('machine learning', http=http)
        self.assertEqual(sources[0].title, 'A paper')
        self.assertEqual(sources[0].url, 'https://arxiv.org/abs/2501.01234')
        self.assertEqual(sources[0].doi, '10.1234/test')
        self.assertEqual(sources[0].providers, ('arXiv',))
        self.assertTrue(sources[0].is_preprint)
        self.assertIn('not necessarily peer reviewed', sources[0].evidence_design)
        self.assertEqual(http.get.call_args.kwargs['params']['search_query'],
                         'all:"machine" AND all:"learning"')

    def test_arxiv_paces_retries_and_stop_interrupts_wait(self):
        http = Mock()
        http.get.side_effect = [requests.Timeout(), Mock(text='<feed xmlns="http://www.w3.org/2005/Atom"/>')]
        with patch('cowriter.research._arxiv_last_request', 99), \
             patch('cowriter.research.monotonic', return_value=100), \
             patch('cowriter.research.sleep') as wait:
            self.assertEqual(search_arxiv('test', http=http), [])
        self.assertEqual([call.args[0] for call in wait.call_args_list], [2, 1, 3])
        cancelled = threading.Event()
        cancelled.set()
        http.reset_mock()
        with self.assertRaises(JobCancelled):
            search_arxiv('test', http=http, cancel_event=cancelled)
        http.get.assert_not_called()

    def test_arxiv_invalid_feed_is_failure_not_zero_matches(self):
        http = Mock()
        http.get.return_value = Mock(text='<html>Service unavailable</html>')
        with patch('cowriter.research._arxiv_last_request', 0):
            with self.assertRaises(ResearchError):
                search_arxiv('test', http=http)

    def test_openalex_restores_abstract_and_retraction_metadata(self):
        response = Mock()
        response.json.return_value = {'results': [{
            'display_name': 'A broad study', 'doi': 'https://doi.org/10.1234/test',
            'publication_year': 2025, 'type': 'article', 'is_retracted': True,
            'authorships': [{'author': {'display_name': 'Writer A'}}],
            'primary_location': {'source': {'display_name': 'A journal'}, 'version': 'publishedVersion'},
            'abstract_inverted_index': {'Study': [0], 'findings': [1], 'matter': [2]},
            'cited_by_count': 7,
        }]}
        http = Mock()
        http.get.return_value = response
        source = search_openalex('climate', http=http)[0]
        self.assertEqual(source.abstract, 'Study findings matter')
        self.assertTrue(source.is_retracted)
        self.assertEqual(source.providers, ('OpenAlex',))
        self.assertEqual(source.journal, 'A journal')
        self.assertEqual(http.get.call_args.kwargs['params'], {'search': 'climate', 'per_page': 4})

    def test_openalex_missing_metadata_and_invalid_response(self):
        response = Mock()
        response.json.return_value = {'results': [{'id': 'https://openalex.org/W1', 'type': 'preprint'}]}
        http = Mock()
        http.get.return_value = response
        source = search_openalex('test', http=http)[0]
        self.assertEqual(source.abstract, '')
        self.assertEqual(source.authors, 'Unknown authors')
        self.assertTrue(source.is_preprint)
        response.json.return_value = {'error': 'unavailable'}
        with self.assertRaises(ResearchError):
            search_openalex('test', http=http)

    def test_deduplication_merges_doi_and_preserves_provenance_and_retraction(self):
        manuscript = EvidenceSource('A paper', 'A', '2025', '', 'Abstract',
            'https://arxiv.org/abs/2501.01234', doi='10.1234/TEST', providers=('arXiv',),
            arxiv_id='2501.01234', is_preprint=True)
        published = EvidenceSource('A paper with changed title', 'A', '2026', 'Journal', '',
            'https://doi.org/10.1234/test', doi='https://doi.org/10.1234/test',
            providers=('OpenAlex',), is_retracted=True)
        result = deduplicate_sources([manuscript, published])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].providers, ('arXiv', 'OpenAlex'))
        self.assertEqual(result[0].abstract, 'Abstract')
        self.assertEqual(result[0].title, published.title)
        self.assertFalse(result[0].is_preprint)
        self.assertTrue(result[0].is_retracted)

    def test_deduplication_respects_distinct_dois_and_merges_identifier_bridges(self):
        first = EvidenceSource('Common title', 'A', '2025', '', '', 'https://doi.org/10.1/a', doi='10.1/a')
        different = replace(first, doi='10.1/b', url='https://doi.org/10.1/b')
        self.assertEqual(len(deduplicate_sources([first, different])), 2)
        manuscript = replace(first, title='Changed title', doi='', arxiv_id='2501.01234')
        bridge = replace(first, arxiv_id='2501.01234')
        self.assertEqual(len(deduplicate_sources([first, manuscript, bridge])), 1)

    def test_search_preserves_partial_results_and_marks_failed_collections(self):
        source = EvidenceSource('Study', 'A', '2025', '', '', 'https://example.com', providers=('OpenAlex',))
        progress = Mock()
        with patch('cowriter.research.search_europe_pmc', side_effect=ResearchError('offline')), \
             patch('cowriter.research.search_arxiv', return_value=[]) as arxiv, \
             patch('cowriter.research.search_openalex', return_value=[source]):
            result = search_evidence('test', providers=['europe_pmc', 'openalex'], on_progress=progress)
        arxiv.assert_not_called()
        self.assertEqual(result.sources, [source])
        self.assertIn('unavailable', result.coverage[0])
        self.assertIn('1 publication', result.coverage[1])
        self.assertEqual(progress.call_count, 2)

    def test_all_failed_collections_are_recorded_and_cancellation_propagates(self):
        with patch('cowriter.research.search_arxiv', side_effect=ResearchError('offline')):
            result = search_evidence('test', providers=['arxiv'])
        self.assertEqual(result.sources, [])
        self.assertIn('unavailable', result.coverage[0])
        with patch('cowriter.research.search_arxiv', side_effect=JobCancelled):
            with self.assertRaises(JobCancelled):
                search_evidence('test', providers=['arxiv'])
        with self.assertRaises(ResearchError):
            search_evidence('test', providers=[])

    def test_report_records_failed_searches_preprints_and_retractions(self):
        source = EvidenceSource('Study', 'A', '2025', '', '', 'https://example.com',
                                providers=('arXiv',), is_preprint=True, is_retracted=True)
        claims = [(ClaimQuery('A claim', 'test'), [source])]
        coverage = [('OpenAlex: unavailable', 'arXiv: 1 publication(s) retrieved')]
        for formatted in (format_evidence(claims, coverage), format_source_record(claims, coverage)):
            self.assertIn('OpenAlex: unavailable', formatted)
            self.assertIn('arXiv', formatted)
            self.assertIn('RETRACTED', formatted)
            self.assertIn('peer review', formatted.lower())

    def test_non_searchable_claims_cannot_send_queries_and_query_length_is_bounded(self):
        claims = parse_claim_queries(json.dumps({'claims': [
            {'claim': 'Personal story', 'kind': 'lived_experience', 'query': 'private identifying text'},
            {'claim': 'Research', 'query': ' '.join(['term'] * 30)}]}))
        self.assertEqual(claims[0].query, '')
        self.assertEqual(len(claims[1].query.split()), 12)

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

    def test_cancelled_search_makes_no_request_and_does_not_retry(self):
        cancelled = threading.Event()
        cancelled.set()
        http = Mock()
        with self.assertRaises(JobCancelled):
            search_europe_pmc("test", http=http, cancel_event=cancelled)
        http.get.assert_not_called()
        cancelled.clear()
        def cancel_during_request(*args, **kwargs):
            cancelled.set()
            raise requests.Timeout("timeout")
        http.get.side_effect = cancel_during_request
        with self.assertRaises(JobCancelled):
            search_europe_pmc("test", http=http, cancel_event=cancelled)
        self.assertEqual(http.get.call_count, 1)

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
