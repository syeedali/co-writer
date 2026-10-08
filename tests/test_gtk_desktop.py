import time
from pathlib import Path
from unittest.mock import Mock, patch

from test_gtk_layout import GtkWindowTestCase
from cowriter.exporting import export_document, import_office_text


class GtkDesktopTests(GtkWindowTestCase):
    def wait_copy(self):
        deadline = time.monotonic() + 5
        while self.win._handoff_busy and time.monotonic() < deadline:
            self.settle()
        self.assertFalse(self.win._handoff_busy)

    def text(self, buf):
        return buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)

    def test_writer_copy_contains_unsaved_edits_and_preserves_original(self):
        page, _, buf = self.win._get_current_page()
        original = Path(self.win.open_tabs[page])
        disk_text = original.read_text()
        buf.set_text("# Unsaved heading\n\nA **revised** passage.", -1)
        with patch.object(self.module.desktop, "writer_app", return_value=Mock()), \
             patch.object(self.module.desktop, "launch_writer") as launch:
            self.win._on_open_writer()
            self.wait_copy()
            launch.assert_called_once()
            copy = launch.call_args.args[0]
        self.assertEqual(copy.parent, self.module.WORK_DIR / "shared")
        self.assertIn("# Unsaved heading", import_office_text(copy))
        self.assertEqual(original.read_text(), disk_text)
        self.assertTrue(buf.get_modified())

    def test_email_selection_includes_only_highlighted_text_and_source_url(self):
        _, _, buf = self.win._get_current_page()
        passage = "A **claim** from a [source](https://example.com/paper)."
        buf.set_text("PRIVATE BEFORE " + passage + " PRIVATE AFTER", -1)
        action = self.win._desktop_actions.lookup_action("email-selection")
        self.assertFalse(action.get_enabled())
        start = len("PRIVATE BEFORE ")
        buf.select_range(buf.get_iter_at_offset(start), buf.get_iter_at_offset(start + len(passage)))
        self.assertTrue(action.get_enabled())
        with patch.object(self.module.desktop, "compose_email") as compose:
            self.win._on_email_selection()
        body = compose.call_args.args[1]
        self.assertIn("claim from a source (https://example.com/paper)", body)
        self.assertNotIn("PRIVATE", body)

    def test_email_attachment_is_separate_current_document_copy(self):
        page, _, buf = self.win._get_current_page()
        original = Path(self.win.open_tabs[page])
        buf.set_text("# Email revision\n\nCurrent **unsaved** text.", -1)
        disk_text = original.read_text()
        with patch.object(self.module.desktop, "compose_email") as compose:
            self.win._on_email_odt()
            self.wait_copy()
            attachment = compose.call_args.kwargs["attachment"]
        self.assertNotEqual(attachment, original)
        self.assertIn("**unsaved**", import_office_text(attachment))
        self.assertEqual(original.read_text(), disk_text)

    def test_failed_export_keeps_editable_draft_and_does_not_launch(self):
        _, _, buf = self.win._get_current_page()
        buf.set_text("Keep unsaved draft", -1)
        with patch.object(self.module, "export_document", side_effect=OSError("disk full")), \
             patch.object(self.win, "_launch_file") as launch, \
             patch.object(self.win, "_show_error") as error:
            self.win._on_open_pdf()
            self.wait_copy()
            launch.assert_not_called()
            error.assert_called_once()
        self.assertEqual(self.text(buf), "Keep unsaved draft")
        self.assertTrue(self.win._desktop_actions.lookup_action("open-pdf").get_enabled())

    def test_import_revision_creates_new_tab_and_preserves_both_sources(self):
        page, _, buf = self.win._get_current_page()
        buf.set_text("Original unsaved draft", -1)
        source = self.module.WORK_DIR / "revised.odt"
        export_document(source, "# Writer revision\n\nA **new** passage.")
        source_bytes = source.read_bytes()
        imported = self.win._import_revised_copy(source)
        new_page, _, new_buf = self.win._get_current_page()
        self.assertNotEqual(page, new_page)
        self.assertNotEqual(source, imported)
        self.assertEqual(self.text(buf), "Original unsaved draft")
        self.assertTrue(buf.get_modified())
        self.assertEqual(source.read_bytes(), source_bytes)
        self.assertIn("# Writer revision", self.text(new_buf))
        self.assertEqual(imported.stat().st_mode & 0o777, 0o600)

    def test_files_action_reveals_original_and_chooser_uses_a_copy(self):
        page, _, buf = self.win._get_current_page()
        original = Path(self.win.open_tabs[page])
        buf.set_text("Unsaved Markdown", -1)
        with patch.object(self.win, "_launch_file") as launch:
            self.win._on_show_file()
            launch.assert_called_once_with(original, folder=True)
            launch.reset_mock()
            self.win._on_open_copy_with()
            self.wait_copy()
            copy = launch.call_args.args[0]
            self.assertEqual(launch.call_args.kwargs, {"choose": True})
            self.assertNotEqual(copy, original)
            self.assertEqual(copy.read_text(), "Unsaved Markdown")
