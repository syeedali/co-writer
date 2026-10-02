"""Display-dependent regression checks for the adaptive editor layout."""

import importlib
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class GtkLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp_dir.cleanup)
        with patch.object(Path, "home", return_value=Path(cls.temp_dir.name)):
            sys.modules.pop("cowriter.gtk_app", None)
            cls.module = importlib.import_module("cowriter.gtk_app")
        if not cls.module.Gtk.init_check():
            raise unittest.SkipTest("GTK layout checks require a display")
        cls.app = cls.module.Adw.Application(
            application_id="com.github.chukrobertson.cowriter.LayoutTests",
            flags=cls.module.Gio.ApplicationFlags.NON_UNIQUE,
        )
        cls.app.register(None)

    def setUp(self):
        with patch.object(self.module.CoWriterWindow, "_refresh_models"), \
             patch.object(self.module.CoWriterWindow, "_schedule_autosave"):
            self.win = self.module.CoWriterWindow(self.app)
        self.addCleanup(self.win.destroy)
        self.win.present()
        self.settle()

    def settle(self):
        context = self.module.GLib.MainContext.default()
        deadline = time.monotonic() + 0.3
        while time.monotonic() < deadline:
            while context.pending():
                context.iteration(False)
            time.sleep(0.005)

    def resize(self, width):
        self.win.set_default_size(width, 700)
        self.settle()

    def test_resize_hides_ai_first_and_restores_panes_without_losing_content(self):
        _, _, buf = self.win._get_current_page()
        buf.set_text("Unsaved draft", -1)
        self.win.chat_entry.set_text("Unsent instruction")
        self.win.chat_buffer.set_text("Existing conversation", -1)
        self.win.chat_history.append({"role": "user", "content": "Keep this"})
        for width, files, ai in [(1400, True, True), (1100, True, False),
                                 (800, False, False), (480, False, False),
                                 (1100, True, False), (1400, True, True)]:
            with self.subTest(width=width):
                self.resize(width)
                self.assertEqual(self.win.files_split.get_show_sidebar(), files)
                self.assertEqual(self.win.ai_split.get_show_sidebar(), ai)
                self.assertEqual(self.win.files_toggle.get_active(), files)
                self.assertEqual(self.win.ai_toggle.get_active(), ai)
                self.assertEqual(self.win.get_width(), width)
                # Header CSS extends over the one-pixel window borders; its
                # minimum request is what determines whether controls clip.
                minimum, _, _, _ = self.win._hb.measure(self.module.Gtk.Orientation.HORIZONTAL, -1)
                self.assertLessEqual(minimum, width)
                self.assertLessEqual(self.win.edit_notebook.get_width(), width)
                self.assertGreater(self.win.edit_notebook.get_width(), 400)
        self.assertEqual(buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False),
                         "Unsaved draft")
        self.assertEqual(self.win.chat_entry.get_text(), "Unsent instruction")
        chat = self.win.chat_buffer
        self.assertEqual(chat.get_text(chat.get_start_iter(), chat.get_end_iter(), False),
                         "Existing conversation")
        self.assertEqual(len(self.win.chat_history), 1)

    def test_narrow_drawers_are_mutually_exclusive_and_close_after_opening_a_file(self):
        self.resize(800)
        self.win.files_toggle.set_active(True)
        self.settle()
        self.assertTrue(self.win.files_split.get_show_sidebar())
        self.win.ai_toggle.set_active(True)
        self.settle()
        self.assertTrue(self.win.ai_split.get_show_sidebar())
        self.assertFalse(self.win.files_split.get_show_sidebar())
        self.win.files_toggle.set_active(True)
        self.settle()
        self.assertFalse(self.win.ai_split.get_show_sidebar())
        # Activate the Drafts/current_draft.md row just as a double click does.
        path = self.module.Gtk.TreePath.new_from_string("0:0:0")
        self.win._on_file_activated(self.win.file_tree, path, None)
        self.assertFalse(self.win.files_split.get_show_sidebar())
        self.assertFalse(self.win.files_toggle.get_active())

    def test_manual_toggles_and_ai_edit_remain_accessible(self):
        self.resize(1400)
        self.win.ai_toggle.set_active(False)
        self.assertFalse(self.win.ai_split.get_show_sidebar())
        self.win.ai_toggle.set_active(True)
        self.assertTrue(self.win.ai_split.get_show_sidebar())
        self.resize(800)
        self.win._on_ai_edit(None)
        self.assertTrue(self.win.ai_split.get_show_sidebar())
        self.assertTrue(self.win.ai_toggle.get_active())


if __name__ == "__main__":
    unittest.main()
