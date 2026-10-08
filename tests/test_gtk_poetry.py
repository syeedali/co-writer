import threading
import time
from unittest.mock import Mock, patch

from test_gtk_layout import GtkWindowTestCase
from cowriter.poetry import RhymeMatches


class GtkPoetryTests(GtkWindowTestCase):
    def open_tools(self, text="The moon is bright\nI walk at night"):
        _, _, buf = self.win._get_current_page()
        buf.set_text(text, -1)
        buf.place_cursor(buf.get_start_iter())
        buf.set_modified(False)
        self.win._on_poetry_tools()
        tools = self.win._poetry_tools
        self.addCleanup(tools.destroy)
        self.wait_for(lambda: tools._result is not None)
        return tools, buf

    def wait_for(self, condition):
        end = time.monotonic() + 6
        while not condition() and time.monotonic() < end:
            self.settle()
        self.assertTrue(condition(), "Poetry tools did not finish")

    def test_tools_are_optional_single_instance_and_never_modify_text(self):
        self.assertIsNone(self.win._poetry_tools)
        tools, buf = self.open_tools()
        original = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
        self.win._on_poetry_tools()
        self.assertIs(self.win._poetry_tools, tools)
        self.assertEqual(len(tools._result.lines), 2)
        self.assertFalse(buf.get_modified())
        tools.destroy()
        self.assertIsNone(self.win._poetry_tools)
        self.assertFalse(buf.get_modified())
        self.assertEqual(buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False), original)

    def test_rhyme_colors_coexist_with_proofreading_and_can_be_toggled(self):
        tools, buf = self.open_tools("i see light\nI walk at night")
        checker = next(iter(self.win._proofreaders.values()))
        self.wait_for(lambda: not checker.checking)
        light = tools._result.lines[0].words[-1]
        night = tools._result.lines[1].words[-1]
        tag = tools._tags["poetry-rhyme-0"]
        self.assertIn(tag, buf.get_iter_at_offset(light.start).get_tags())
        self.assertIn(tag, buf.get_iter_at_offset(night.start).get_tags())
        self.assertIn(checker._tags["grammar"], buf.get_start_iter().get_tags())
        tools.rhythm_colors.set_active(True)
        self.assertTrue(tools.color_legend.get_visible())
        self.assertIn(tools._tags["poetry-strong"], buf.get_start_iter().get_tags())
        tools.rhyme_colors.set_active(False)
        self.assertNotIn(tag, buf.get_iter_at_offset(light.start).get_tags())
        tools.destroy()
        self.assertIn(checker._tags["grammar"], buf.get_start_iter().get_tags())

    def test_selection_offsets_and_line_numbers_are_preserved(self):
        text = "😀 An introduction\n\nThe moon is bright\nI walk at night\n"
        tools, buf = self.open_tools(text)
        start = text.index("The moon")
        buf.select_range(buf.get_iter_at_offset(start), buf.get_end_iter())
        tools.scope.set_selected(1)
        self.wait_for(lambda: tools._request and tools._request[0] == start)
        self.assertEqual(len(tools._result.lines), 2)
        self.assertEqual(tools._request[1], 2)
        word = tools._result.lines[0].words[-1]
        self.assertIn(tools._tags["poetry-rhyme-0"], buf.get_iter_at_offset(start + word.start).get_tags())
        self.assertNotIn(tools._tags["poetry-rhyme-0"], buf.get_start_iter().get_tags())

    def test_current_stanza_follows_cursor_and_updates_after_editing(self):
        tools, buf = self.open_tools("light\nnight\n\nmoon\nspoon")
        self.assertEqual([line.words[-1].text for line in tools._result.lines], ["light", "night"])
        buf.place_cursor(buf.get_end_iter())
        self.wait_for(lambda: tools._result and tools._result.lines[0].words[0].text == "moon")
        buf.insert_at_cursor("\ntune", -1)
        self.wait_for(lambda: tools._result and len(tools._result.lines) == 3)
        self.assertTrue(buf.get_modified())

    def test_tab_switch_removes_old_colors_and_follows_active_document(self):
        tools, old = self.open_tools("light\nnight")
        tag = tools._tags["poetry-rhyme-0"]
        path = self.module.WORK_DIR / "poem.md"
        path.write_text("moon\nspoon")
        self.win._open_document(path)
        self.wait_for(lambda: tools._result and tools._result.lines[0].words[0].text == "moon")
        self.assertIs(tools._buffer, self.win._get_current_page()[2])
        self.assertNotIn(tag, old.get_start_iter().get_tags())
        self.assertFalse(tools._buffer.get_modified())

    def test_rhyme_lookup_uses_selection_and_copy_does_not_edit(self):
        tools, buf = self.open_tools("light\nnight")
        buf.select_range(buf.get_start_iter(), buf.get_iter_at_offset(5))
        tools.use_editor_word()
        self.assertEqual(tools.rhyme_entry.get_text(), "light")
        self.wait_for(lambda: tools.exact_words.get_first_child() is not None)
        self.assertIn("light", tools.rhyme_status.get_label())
        child = tools.exact_words.get_first_child()
        labels = []
        while child:
            labels.append(child.get_child().get_label())
            child = child.get_next_sibling()
        self.assertIn("night", labels)
        clipboard = Mock()
        with patch.object(tools, "get_clipboard", return_value=clipboard):
            tools._copy_word("night")
        clipboard.set.assert_called_once_with("night")
        self.assertFalse(buf.get_modified())
        self.assertEqual(buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False), "light\nnight")

    def test_unknown_rhyme_word_is_explained_without_guessed_matches(self):
        tools, _ = self.open_tools()
        tools.rhyme_entry.set_text("zzyxxyq")
        self.wait_for(lambda: "not in the dictionary" in tools.rhyme_status.get_label())
        self.assertIsNone(tools.exact_words.get_first_child())
        self.assertIsNone(tools.echo_words.get_first_child())

    def test_empty_selection_and_no_open_document_are_handled(self):
        tools, _ = self.open_tools()
        tools.scope.set_selected(1)
        self.wait_for(lambda: "Select a passage" in tools.summary.get_label())
        self.assertIsNone(tools._result)
        for page in list(self.win.open_tabs):
            self.win._remove_tab(page)
        self.wait_for(lambda: "Open a document" in tools.summary.get_label())
        self.assertIsNone(tools._buffer)

    def test_plain_editor_and_large_passages_show_bounded_excerpts(self):
        path = self.module.WORK_DIR / "plain.txt"
        path.write_text("light\nnight\n" * 120)
        with patch.object(self.module, "HAS_GTKSOURCE", False):
            self.win._open_document(path)
        self.win._on_poetry_tools()
        tools = self.win._poetry_tools
        self.addCleanup(tools.destroy)
        tools.scope.set_selected(2)
        self.wait_for(lambda: tools._result is not None)
        self.assertIn("Showing an excerpt", tools.summary.get_label())
        count, row = 0, tools.line_list.get_first_child()
        while row:
            count += 1
            row = row.get_next_sibling()
        self.assertEqual(count, tools.MAX_LINES)
        self.assertFalse(tools._buffer.get_modified())

    def test_background_worker_rejects_stale_results_and_close_is_safe(self):
        from cowriter.gtk_poetry import LatestWorker
        started, release = threading.Event(), threading.Event()
        outputs = []

        def slow(request):
            if request == "old":
                started.set()
                release.wait(3)
            return request

        worker = LatestWorker(slow, lambda request, result, error: outputs.append(result))
        self.addCleanup(worker.close)
        worker.submit("old")
        self.assertTrue(started.wait(1))
        worker.submit("obsolete")
        worker.submit("new")
        release.set()
        self.wait_for(lambda: outputs == ["new"])
        worker.submit("late")
        worker.close()
        self.settle()
        self.assertEqual(outputs, ["new"])

    def test_shortcut_and_owner_destruction_cleanup(self):
        tools, _ = self.open_tools()
        self.assertIn("<Control><Alt>p", self.app.get_accels_for_action("win.poetry-tools"))
        self.win.destroy()
        self.assertTrue(tools._closed)
        self.assertTrue(tools._analysis.closed)
        self.assertTrue(tools._rhymes.closed)
