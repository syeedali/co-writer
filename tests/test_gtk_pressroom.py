import json
from pathlib import Path
from unittest.mock import patch
from test_gtk_layout import GtkWindowTestCase
from cowriter.research import ClaimQuery, EvidenceSource


class GtkPressroomTests(GtkWindowTestCase):
    def test_send_includes_unsaved_article_and_only_its_research(self):
        page, _, buf = self.win._get_current_page()
        source = self.win.open_tabs[page]
        original = Path(source).read_text()
        buf.set_text("## Substack draft\n\nUnsaved wording [1].", -1)
        module = self.module
        with patch.object(module.pressroom, "launch") as launch:
            self.win._desktop_actions.lookup_action("send-pressroom").activate(None)
        package = json.loads(Path(launch.call_args.args[0]).read_text())
        self.assertEqual(package["markdown"], "## Substack draft\n\nUnsaved wording [1].")
        self.assertEqual(package["audits"], [])
        self.assertEqual(Path(source).read_text(), original)
        self.assertTrue(buf.get_modified())

    def test_review_snapshot_stays_attached_to_origin_when_report_opens_and_save_as(self):
        page, _, buf = self.win._get_current_page()
        source = self.win.open_tabs[page]
        passage = "Reviewed claim."
        draft = "Earlier text.\n\n" + passage
        buf.set_text(draft, -1)
        context = {"source": source, "document": draft, "passage": passage,
                   "scope": "the selected passage", "model": "local-test"}
        claims = [(ClaimQuery(passage, "neutral query"), [EvidenceSource(
            "Test source", "Author", "2026", "Journal", "Synthetic test abstract",
            "https://example.org/source")])]
        self.win._save_evidence_audit(self.win.evidence_button, "Not verified.", claims,
                                     [("OpenAlex unavailable",)], context)
        report_page, _, _ = self.win._get_current_page()
        self.assertIsNot(report_page, page)
        self.assertEqual(self.module.pressroom.load_reviews(self.module.WORK_DIR / "research", self.win.open_tabs[report_page]), [])
        reviews = self.module.pressroom.load_reviews(self.module.WORK_DIR / "research", source)
        self.assertEqual(reviews[0]["reviewed_passage"], passage)
        self.win.edit_notebook.set_current_page(self.win.edit_notebook.page_num(page))
        buf.set_text(draft + "\n\nNew claim after audit.", -1)
        destination = self.module.WORK_DIR / "renamed.md"
        self.win._save_page(page, destination=destination)
        with patch.object(self.module.pressroom, "launch") as launch:
            self.win._on_send_pressroom()
        package = json.loads(Path(launch.call_args.args[0]).read_text())
        self.assertEqual(package["source_document"], str(destination.resolve()))
        self.assertNotEqual(package["markdown"], package["audits"][0]["reviewed_document"])
        self.assertEqual(package["audits"][0]["claims"][0]["coverage"], ["OpenAlex unavailable"])

    def test_fact_check_captures_original_full_draft_and_selected_scope(self):
        page, _, buf = self.win._get_current_page()
        text = "Unreviewed introduction.\n\nSelected claim."
        buf.set_text(text, -1)
        start = buf.get_iter_at_offset(text.index("Selected"))
        buf.select_range(start, buf.get_end_iter())
        with patch.object(self.win, "_call_ollama"):
            self.win._on_fact_check(self.win.evidence_button)
        context = self.win._job.research_context
        self.assertEqual(context["source"], self.win.open_tabs[page])
        self.assertEqual(context["document"], text)
        self.assertEqual(context["passage"], "Selected claim.")
        self.assertEqual(context["scope"], "the selected passage")
        self.win._on_stop_ai()

    def test_missing_app_reports_saved_package_for_manual_import(self):
        _, _, buf = self.win._get_current_page()
        buf.set_text("An article.", -1)
        with patch.object(self.module.pressroom, "launch", side_effect=RuntimeError("No app")), \
             patch.object(self.win, "_show_error") as error:
            self.win._on_send_pressroom()
        self.assertIn("Article package saved at", error.call_args.args[1])
        self.assertEqual(len(list((self.module.WORK_DIR / "shared" / "pressroom").glob("*.json"))), 1)
