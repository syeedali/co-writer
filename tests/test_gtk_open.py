"""Desktop file opening must deliver documents without replacing unsaved tabs."""
import sys
from pathlib import Path
from unittest.mock import Mock, patch

from test_gtk_layout import GtkWindowTestCase


class GtkFileOpenTests(GtkWindowTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.app = cls.module.CoWriterApp()
        cls.app.set_application_id("com.github.chukrobertson.cowriter.TestFileOpening")
        cls.app.set_flags(cls.module.Gio.ApplicationFlags.HANDLES_OPEN |
                          cls.module.Gio.ApplicationFlags.NON_UNIQUE)
        cls.app.register(None)

    def test_desktop_open_preserves_unsaved_tab_and_selects_requested_file(self):
        old_page, _, old_buf = self.win._get_current_page()
        old_buf.set_text("An unsaved draft that must survive", -1)
        source = self.module.WORK_DIR / "A document with spaces.md"
        source.write_text("# Requested document\n\nCorrect content.")
        self.app.open([self.module.Gio.File.new_for_path(str(source))], "")
        self.settle()
        page, _, buf = self.win._get_current_page()
        self.assertNotEqual(page, old_page)
        self.assertEqual(Path(self.win.open_tabs[page]), source)
        self.assertIn("Correct content.", buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False))
        self.assertEqual(old_buf.get_text(old_buf.get_start_iter(), old_buf.get_end_iter(), False),
                         "An unsaved draft that must survive")
        self.assertTrue(old_buf.get_modified())
        count = self.win.edit_notebook.get_n_pages()
        self.app.open([self.module.Gio.File.new_for_path(str(source))], "")
        self.settle()
        self.assertEqual(self.win.edit_notebook.get_n_pages(), count)

    def test_epub_open_reads_publication_and_preserves_archive(self):
        import zipfile
        source = self.module.WORK_DIR / "A sample book.epub"
        with zipfile.ZipFile(source, "w") as epub:
            epub.writestr("chapter.xhtml", "<html><body><h1>My chapter</h1><p>A &amp; B.</p></body></html>")
        original = source.read_bytes()
        self.app.open([self.module.Gio.File.new_for_path(str(source))], "")
        self.settle()
        page, _, buf = self.win._get_current_page()
        self.assertEqual(Path(self.win.open_tabs[page]), source)
        self.assertIn("My chapter", buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False))
        self.assertIn("A & B.", buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False))
        self.assertEqual(source.read_bytes(), original)
        # Editing an imported ebook saves a text copy, not over the EPUB.
        with patch.object(self.win, "_save_page_as") as save_as:
            self.win._save_page(page)
            save_as.assert_called_once()
        self.assertEqual(source.read_bytes(), original)

    def test_invalid_open_does_not_create_an_error_document(self):
        count = self.win.edit_notebook.get_n_pages()
        with patch.object(self.win, "_show_error") as error:
            self.app.open([self.module.Gio.File.new_for_path(str(self.module.WORK_DIR / "missing.epub"))], "")
            self.settle()
            error.assert_called_once()
        self.assertEqual(self.win.edit_notebook.get_n_pages(), count)

    def test_launcher_accepts_files_and_main_passes_arguments(self):
        desktop = Path(__file__).resolve().parents[1] / "data/com.github.chukrobertson.cowriter.desktop"
        launcher = self.module.Gio.DesktopAppInfo.new_from_filename(str(desktop))
        self.assertTrue(launcher.supports_files())
        app = Mock()
        with patch.object(self.module, "CoWriterApp", return_value=app), \
             patch.object(sys, "argv", ["cowriter-gui", "/tmp/A book.epub"]):
            self.module.main()
        app.run.assert_called_once_with(["cowriter-gui", "/tmp/A book.epub"])
