import time
from pathlib import Path
from unittest.mock import patch

from test_gtk_layout import GtkWindowTestCase
from cowriter.workspace import load_json


class GtkCraftTests(GtkWindowTestCase):
    def wait_for(self, condition):
        deadline = time.monotonic() + 6
        while not condition() and time.monotonic() < deadline:
            self.settle()
        self.assertTrue(condition(), "Craft tools did not finish")

    def open_tools(self, text="fire\nlight\nnight\ntime\nlight"):
        _, _, buf = self.win._get_current_page()
        buf.set_text(text, -1)
        buf.place_cursor(buf.get_start_iter())
        buf.set_modified(False)
        self.win._on_poetry_tools()
        tools = self.win._poetry_tools
        self.addCleanup(tools.destroy)
        self.wait_for(lambda: tools._result is not None)
        return tools, buf

    def test_my_reading_controls_change_hints_and_pauses_without_editing_manuscript(self):
        tools, buf = self.open_tools()
        source = Path(self.win.open_tabs[self.win._get_current_page()[0]])
        original_file = source.read_text()
        spin = tools.reading_words.get_first_child().get_first_child().get_last_child()
        spin.set_value(1)
        self.assertEqual(tools._personal_line(tools._result.lines[0]).syllables, "1")
        tools._change_reading(0, "pause", 1, tools._request)
        self.assertIn("|", tools._line_marks(tools._result.lines[0]))
        marks = tools.reading_words.get_first_child().get_first_child().get_next_sibling()
        marks.get_first_child().get_child().emit("clicked")
        self.assertEqual(tools._personal_line(tools._result.lines[0]).words[0].stresses, ("2",))
        self.assertFalse(buf.get_modified())
        self.assertEqual(buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False), "fire\nlight\nnight\ntime\nlight")
        self.assertEqual(source.read_text(), original_file)
        self.assertEqual(tools._notes.path.stat().st_mode & 0o777, 0o600)

    def test_reading_and_focus_notes_survive_closing_and_reopening(self):
        tools, buf = self.open_tools("fire\nlight")
        tools._change_reading(0, "count", 1, tools._request)
        tools.focus_entry.set_text("Where do I breathe?")
        tools.craft_note.get_buffer().set_text("One question this pass.", -1)
        notes_path = tools._notes.path
        tools.close()
        self.settle()
        self.assertEqual(load_json(notes_path)["focus"], "Where do I breathe?")
        self.assertIsNone(self.win._poetry_tools)
        self.win._on_poetry_tools()
        reopened = self.win._poetry_tools
        self.addCleanup(reopened.destroy)
        self.wait_for(lambda: reopened._result is not None)
        self.assertEqual(reopened.focus_entry.get_text(), "Where do I breathe?")
        self.assertEqual(reopened._personal_line(reopened._result.lines[0]).syllables, "1")
        reopened._reset_reading()
        self.assertEqual(reopened._personal_line(reopened._result.lines[0]).syllables, "1–2")
        self.assertFalse(buf.get_modified())

    def test_changed_line_holds_reading_aside_and_insertion_preserves_other_line(self):
        tools, buf = self.open_tools("fire\nlight")
        tools._change_reading(0, "count", 1, tools._request)
        buf.set_text("Opening\nfire\nlight", -1)
        self.wait_for(lambda: tools._result and len(tools._result.lines) == 3)
        self.assertEqual(tools._personal_line(tools._result.lines[1]).syllables, "1")
        buf.set_text("Opening\nfires\nlight", -1)
        self.wait_for(lambda: tools._result and tools._result.lines[1].text == "fires")
        self.assertIsNone(tools._line_record(tools._result.lines[1]))
        self.assertIn("kept aside", tools.bookmark_list.get_first_child().get_label())

    def test_partial_line_selection_cannot_attach_marks_to_unselected_words(self):
        tools, buf = self.open_tools("A little fire\nlight")
        buf.select_range(buf.get_iter_at_offset(9), buf.get_iter_at_offset(13))
        tools.scope.set_selected(1)
        self.wait_for(lambda: tools._result and tools._request[0] == 9)
        self.assertIsNone(tools._selected_reading())
        self.assertIn("complete line", tools.reading_summary.get_label())

    def test_rhyme_map_and_manual_gap_labels_persist(self):
        tools, buf = self.open_tools()
        self.assertIn("connection", tools.map_summary.get_label())
        tools.pair_left.set_selected(0)
        tools.pair_right.set_selected(1)
        tools.pair_kind.set_selected(2)
        tools._remember_pair()
        record = load_json(tools._notes.path)["pairs"][0]
        self.assertEqual(record["label"], "Intentional gap")
        labels = []
        child = tools.map_list.get_first_child()
        while child:
            if hasattr(child, "get_child") and child.get_child() and hasattr(child.get_child(), "get_label"):
                labels.append(child.get_child().get_label())
            child = child.get_next_sibling()
        self.assertTrue(any("Your choice: Intentional gap" in text for text in labels))
        self.assertFalse(buf.get_modified())

    def test_repetition_highlights_and_motif_notes_are_optional_and_not_exported(self):
        tools, buf = self.open_tools("My lantern is glowing.\nHer lantern is glowing.")
        tools.repeat_size.set_selected(2)
        group = tools.repeat_list.get_first_child()
        self.assertIn("lantern is glowing", group.get_label())
        children = group.get_child()
        children.get_first_child().emit("clicked")
        start = tools._repeat_group.spans[0][0]
        self.assertIn(tools._tags["poetry-repeat"], buf.get_iter_at_offset(start).get_tags())
        children.get_first_child().get_next_sibling().set_active(True)
        self.assertEqual(load_json(tools._notes.path)["motifs"], [{"phrase": "lantern is glowing"}])
        tools.destroy()
        self.assertNotIn(buf.get_tag_table().lookup("poetry-repeat"), buf.get_iter_at_offset(start).get_tags())
        self.assertFalse(buf.get_modified())

    def test_bookmarks_follow_unique_lines_and_changed_bookmarks_stay_disabled(self):
        tools, buf = self.open_tools("Opening\nA unique movement\nEnding")
        buf.place_cursor(buf.get_iter_at_offset(len("Opening\n")))
        tools.bookmark_entry.set_text("Second movement")
        tools._bookmark()
        record = tools._notes.data["bookmarks"][0]
        buf.set_text("New opening\nOpening\nA unique movement\nEnding", -1)
        self.wait_for(lambda: tools._result and len(tools._result.lines) == 4)
        tools._visit_bookmark(record)
        self.assertEqual(buf.get_iter_at_mark(buf.get_insert()).get_offset(), len("New opening\nOpening\n"))
        buf.set_text("New opening\nOpening\nA changed movement\nEnding", -1)
        self.wait_for(lambda: tools._result and "changed" in tools._request[2])
        button = tools.bookmark_list.get_first_child().get_first_child()
        self.assertFalse(button.get_sensitive())

    def test_notes_follow_save_as_and_stay_separate_between_tabs(self):
        tools, _ = self.open_tools()
        tools.focus_entry.set_text("Follow the breaths")
        original_path = tools._notes.path
        page = self.win._get_current_page()[0]
        new_source = self.module.WORK_DIR / "renamed.md"
        self.win.open_tabs[page] = str(new_source)
        self.win._update_status_bar()
        self.assertNotEqual(tools._notes.path, original_path)
        self.assertEqual(load_json(tools._notes.path)["focus"], "Follow the breaths")
        other = self.module.WORK_DIR / "other.md"
        other.write_text("Another poem")
        self.win._open_document(other)
        self.settle()
        self.assertEqual(tools.focus_entry.get_text(), "")
        self.assertEqual(load_json(original_path)["focus"], "Follow the breaths")

    def test_failed_note_save_remains_retryable_and_does_not_close_window(self):
        tools, buf = self.open_tools()
        tools.focus_entry.set_text("Keep this note")
        with patch.object(tools._notes, "save", side_effect=OSError("disk full")):
            self.assertTrue(tools._closing())
            self.assertFalse(tools._closed)
            self.assertTrue(tools._notes.dirty)
            self.assertTrue(self.win._on_close_request(self.win))
        self.assertTrue(tools.flush_craft_notes())
        self.assertEqual(load_json(tools._notes.path)["focus"], "Keep this note")
        self.assertFalse(buf.get_modified())

    def test_reference_cards_and_tool_selector_fit_a_small_window(self):
        tools, _ = self.open_tools()
        self.assertEqual(tools.tool_choice.get_model().get_n_items(), 7)
        for index in range(7):
            tools.tool_choice.set_selected(index)
            tools.set_default_size(380, 600)
            self.settle()
            self.assertLessEqual(tools.get_width(), 380)

    def test_old_controls_cannot_annotate_a_new_revision_or_another_selected_line(self):
        tools, buf = self.open_tools("fire\nlight")
        old_request = tools._request
        tools.reading_line.set_selected(1)
        tools._change_reading(0, "count", 4, old_request, target=0)
        self.assertEqual(tools._notes.data["readings"], [])
        buf.set_text("fire\nlight", -1)
        self.wait_for(lambda: tools._result is not None)
        tools._change_reading(0, "count", 4, old_request)
        self.assertEqual(tools._notes.data["readings"], [])

    def test_rhyme_lookup_can_be_filtered_by_syllable_count(self):
        tools, _ = self.open_tools()
        tools.rhyme_entry.set_text("light")
        tools.rhyme_syllables.set_selected(2)
        self.wait_for(lambda: "2 syllable(s)" in tools.rhyme_status.get_label())
        labels, child = [], tools.exact_words.get_first_child()
        while child:
            labels.append(child.get_child().get_label())
            child = child.get_next_sibling()
        self.assertIn("alight", labels)
        self.assertNotIn("night", labels)

    def test_chosen_syllable_count_keeps_unknown_stress_gray(self):
        tools, buf = self.open_tools("zzyxxyq")
        tools._change_reading(0, "count", 1, tools._request)
        tools.rhythm_colors.set_active(True)
        self.assertIn(tools._tags["poetry-unknown"], buf.get_start_iter().get_tags())
        self.assertNotIn(tools._tags["poetry-strong"], buf.get_start_iter().get_tags())
        self.assertNotIn("estimated", tools.summary.get_label())
