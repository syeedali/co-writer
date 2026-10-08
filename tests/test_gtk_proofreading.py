import threading
import time
from unittest.mock import patch

from test_gtk_layout import GtkWindowTestCase
from cowriter.proofreading import CheckResult, Issue


class GtkProofreadingTests(GtkWindowTestCase):
    def current(self):
        page, view, buf = self.win._get_current_page()
        return self.win._proofreaders[page], view, buf

    def checked(self, checker):
        deadline = time.monotonic() + 4
        while checker.checking and time.monotonic() < deadline:
            self.settle()
        self.assertFalse(checker.checking, "Proofreading did not finish")

    def test_open_document_gets_underlines_without_becoming_modified(self):
        path = self.module.WORK_DIR / "typos.md"
        path.write_text("Misspealling grammer. i dont know.")
        self.win._open_document(path)
        checker, _, buf = self.current()
        self.checked(checker)
        self.assertEqual([i.kind for i in checker.issues], ["spelling", "spelling", "grammar", "grammar"])
        for issue in checker.issues:
            self.assertIn(checker._tags[issue.kind], buf.get_iter_at_offset(issue.start).get_tags())
        self.assertFalse(buf.get_modified())
        self.assertEqual(path.read_text(), "Misspealling grammer. i dont know.")
        self.assertEqual(self.win.proofreading_status.get_label(), "4 issues")

    def test_popup_correction_is_explicit_and_one_undo_restores_text(self):
        checker, _, buf = self.current()
        original = "😀 Café. i dont know."
        buf.set_text(original, -1)
        self.checked(checker)
        issue = next(i for i in checker.issues if original[i.start:i.end] == "dont")
        checker.show_issue(issue)
        self.assertTrue(checker._popover.get_visible())
        button = checker._popover.get_child().get_first_child().get_next_sibling()
        self.assertEqual(button.get_label(), "don't")
        button.emit("clicked")
        self.assertEqual(buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False), "😀 Café. i don't know.")
        self.assertTrue(buf.get_modified())
        buf.undo()
        self.assertEqual(buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False), original)

    def test_old_results_and_corrections_cannot_affect_a_new_revision(self):
        checker, _, buf = self.current()
        buf.set_text("i dont know.", -1)
        self.checked(checker)
        issue = checker.issues[0]
        old_generation = checker._generation
        buf.set_text("Correct text.", -1)
        checker._finish(old_generation, CheckResult((issue,)))
        checker.replace(issue, "I", old_generation)
        self.assertEqual(checker.issues, ())
        self.assertEqual(buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False), "Correct text.")
        self.assertNotIn(checker._tags["grammar"], buf.get_start_iter().get_tags())

    def test_slow_checker_keeps_only_latest_request_and_closing_is_safe(self):
        checker, _, buf = self.current()
        started, release = threading.Event(), threading.Event()

        def slow(text, **_kwargs):
            started.set()
            release.wait(3)
            return CheckResult((Issue(0, 1, "grammar", "Capitalize I", ("I",)),))

        with patch("cowriter.gtk_proofreading.check_text", side_effect=slow):
            buf.set_text("i first", -1)
            checker._start()
            self.assertTrue(started.wait(1))
            buf.set_text("i second", -1)
            checker._start()
            buf.set_text("i latest", -1)
            checker._start()
            self.assertEqual(checker._pending[1], "i latest")
            checker.close()
            release.set()
            self.settle()
            self.assertEqual(checker.issues, ())
            self.assertIsNone(checker._pending)

    def test_toggle_clears_underlines_and_is_saved(self):
        checker, _, buf = self.current()
        buf.set_text("i dont know", -1)
        self.checked(checker)
        action = self.win._desktop_actions.lookup_action("proofreading")
        action.change_state(self.module.GLib.Variant("b", False))
        self.assertEqual(checker.issues, ())
        self.assertFalse(checker.enabled)
        self.assertFalse(self.module.load_config()["proofreading"])
        self.assertEqual(self.win.proofreading_status.get_label(), "Checking off")
        action.change_state(self.module.GLib.Variant("b", True))
        self.checked(checker)
        self.assertEqual(len(checker.issues), 2)

    def test_personal_dictionary_persists_and_applies_to_all_tabs(self):
        checker, _, buf = self.current()
        buf.set_text("Membrie", -1)
        self.checked(checker)
        self.assertEqual(len(checker.issues), 1)
        second = self.module.WORK_DIR / "second.md"
        second.write_text("MEMBRIE")
        self.win._open_document(second)
        other, _, _ = self.current()
        self.checked(other)
        self.win._learn_spelling("Membrie")
        self.checked(checker)
        self.checked(other)
        self.assertEqual(checker.issues, ())
        self.assertEqual(other.issues, ())
        words = self.module.load_json(self.module.DATA_DIR / "proofreading-words.json")
        self.assertEqual(words["words"], ["Membrie"])
        self.assertEqual((self.module.DATA_DIR / "proofreading-words.json").stat().st_mode & 0o777, 0o600)

    def test_plain_gtk_editor_supports_highlights_and_tab_close_cleans_up(self):
        path = self.module.WORK_DIR / "plain.txt"
        path.write_text("i dont know")
        with patch.object(self.module, "HAS_GTKSOURCE", False):
            page = self.win._open_document(path)
        checker, _, buf = self.current()
        self.checked(checker)
        self.assertEqual(len(checker.issues), 2)
        self.assertFalse(buf.get_modified())
        self.win._remove_tab(page)
        self.assertTrue(checker._closed)
        self.assertNotIn(page, self.win._proofreaders)

    def test_missing_spelling_backend_is_visible_but_grammar_remains(self):
        checker, _, buf = self.current()
        with patch("cowriter.proofreading.subprocess.run", side_effect=FileNotFoundError()):
            buf.set_text("i dont know", -1)
            self.checked(checker)
        self.assertEqual(len(checker.issues), 2)
        self.assertEqual(self.win.proofreading_status.get_label(), "Check limited")
        self.assertIn("aspell", self.win.proofreading_status.get_tooltip_text())

    def test_f7_opens_corrections_for_the_active_tab(self):
        checker, _, buf = self.current()
        buf.set_text("Good. i dont know", -1)
        buf.place_cursor(buf.get_start_iter())
        self.checked(checker)
        self.assertIn("F7", self.app.get_accels_for_action("win.next-writing-issue"))
        self.win._next_writing_issue()
        self.assertEqual(buf.get_iter_at_mark(buf.get_insert()).get_offset(), 6)
        self.assertTrue(checker._popover.get_visible())
        self.win._next_writing_issue()
        self.assertEqual(buf.get_iter_at_mark(buf.get_insert()).get_offset(), 8)
