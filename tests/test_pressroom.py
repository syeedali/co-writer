import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cowriter import pressroom
from cowriter.research import ClaimQuery, EvidenceSource


class ArticleTransferTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.directory = Path(self.root.name)
        self.source = self.directory / "article.md"
        self.text = "## Café article\n\nA claim [1]. [Source](https://example.org/source)."
        self.context = {"source": str(self.source), "document": self.text,
                        "passage": "A claim [1].", "scope": "the selected passage", "model": "local-test"}
        self.record = pressroom.review_record(self.context, "Mixed — assess relevance.",
            "# TEST REVIEW\n\nMixed; no automatic verification.",
            [(ClaimQuery("A claim", "neutral query"), [EvidenceSource(
                "Synthetic test source", "Test Author", "2026", "Test Journal",
                "Fixture only; not real evidence.", "https://example.org/source", providers=("openalex",))])],
            [("OpenAlex: searched; arXiv: unavailable",)])

    def test_structured_sources_and_original_scope_survive_private_transfer(self):
        pressroom.save_review(self.directory / "research", self.source, self.record)
        reviews = pressroom.load_reviews(self.directory / "research", self.source)
        path = pressroom.write_package(self.directory / "shared", "Café article", self.text, self.source, reviews)
        package = json.loads(path.read_text())
        self.assertEqual(package["markdown"], self.text)
        self.assertEqual(package["audits"][0]["reviewed_document"], self.text)
        self.assertEqual(package["audits"][0]["scope"], "the selected passage")
        self.assertEqual(package["audits"][0]["claims"][0]["sources"][0]["abstract"], "Fixture only; not real evidence.")
        self.assertEqual(package["audits"][0]["claims"][0]["coverage"], ["OpenAlex: searched; arXiv: unavailable"])
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertFalse(self.source.exists())

    def test_reviews_are_document_specific_and_follow_save_as(self):
        research = self.directory / "research"
        pressroom.save_review(research, self.source, self.record)
        other = self.directory / "other" / "article.md"
        self.assertEqual(pressroom.load_reviews(research, other), [])
        pressroom.copy_reviews(research, self.source, other)
        self.assertEqual(pressroom.load_reviews(research, other), pressroom.load_reviews(research, self.source))
        edited = self.text + "\n\nChanged wording."
        package = json.loads(pressroom.article_package("Title", edited, other, pressroom.load_reviews(research, other)))
        self.assertNotEqual(package["markdown"], package["audits"][0]["reviewed_document"])

    def test_blank_and_oversized_articles_fail_before_creating_a_copy(self):
        for text in (" ", "x" * 1_000_001, "bad\0text"):
            with self.assertRaises(ValueError):
                pressroom.write_package(self.directory / "shared", "Title", text, self.source)
        self.assertFalse((self.directory / "shared").exists())

    def test_launcher_passes_literal_argv_and_missing_app_has_actionable_error(self):
        filename = self.directory / "spaces $(literal).cowriter-article.json"
        with patch.object(pressroom, "executable", return_value="/tmp/Native App"), \
             patch.object(pressroom.subprocess, "Popen") as launch:
            pressroom.launch(filename)
        self.assertEqual(launch.call_args.args[0], ["/tmp/Native App", "--import-cowriter", str(filename)])
        self.assertNotIn("shell", launch.call_args.kwargs)
        with patch.dict(os.environ, {"OPEN_PRESSROOM_EXECUTABLE": "/not/an/app"}), \
             patch.object(pressroom.shutil, "which", return_value=None), \
             patch.object(Path, "is_file", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "imported manually"):
                pressroom.executable()


class LegacyReportTests(unittest.TestCase):
    def test_manual_attachment_preserves_report_without_inventing_claims_or_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "audit.md"
            text = "# Co-Writer Evidence Audit\n\nGenerated: 2026-10-04 11:00\n\nMixed [1]. https://example.org/source"
            report.write_text(text)
            review = pressroom.attach_report(root / "research", root / "article.md", report)
            self.assertEqual(review["report"], text)
            self.assertEqual(review["reviewed_document"], "")
            self.assertEqual(review["reviewed_passage"], "")
            self.assertEqual(review["claims"], [])
            self.assertIn("not recorded", review["scope"])
            self.assertEqual(review["generated_at"], "2026-10-04 11:00")
            report.write_text("Unrelated text")
            with self.assertRaisesRegex(ValueError, "Evidence Audit"):
                pressroom.attach_report(root / "research", root / "article.md", report)

if __name__ == "__main__":
    unittest.main()
