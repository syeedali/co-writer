"""Optional, writer-controlled views for the existing poetry workbench."""

from gi.repository import Adw, GLib, Gtk

from .craft import (CraftNotes, REFERENCE_CARDS, anchor_at, apply_reading,
                    line_locations, repetitions, resolve_anchor, rhyme_connections)
from .poetry import STRESS_SYMBOLS


class CraftToolsMixin:
    def _init_craft(self, directory):
        self._notes_directory = directory
        self._notes_cache = {}
        self._notes = None
        self._notes_timer = None
        self._loading_notes = False
        self._reading_updating = False
        self._reading_index = 0
        self._repeat_group = None

    def _craft_page(self, description):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                      margin_start=10, margin_end=10, margin_top=10, margin_bottom=10)
        box.append(self.label(description))
        scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(box)
        return scroll, box

    def _build_craft(self):
        pages = []
        page, box = self._craft_page("Explore connections between line endings, including lines farther apart. Your labels are private notes.")
        pages.append(("Rhyme map", page))
        box.append(self.label("Choose any two lines to name a connection."))
        self.pair_left = Gtk.DropDown.new_from_strings(["Choose a line"])
        self.pair_right = Gtk.DropDown.new_from_strings(["Choose a line"])
        self.pair_kind = Gtk.DropDown.new_from_strings(["Rhyme", "Loose rhyme", "Intentional gap"])
        for control in (self.pair_left, self.pair_right, self.pair_kind):
            box.append(control)
        add = Gtk.Button(label="Remember connection")
        add.connect("clicked", lambda *_: self._remember_pair())
        box.append(add)
        self.map_summary = self.label("Explore a passage to see its line endings.")
        box.append(self.map_summary)
        self.map_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.append(self.map_list)

        page, box = self._craft_page("Notice returning words and phrases. Repetition can carry a story or become a refrain.")
        pages.append(("Repetitions", page))
        self.repeat_size = Gtk.DropDown.new_from_strings(["Words", "Two-word phrases", "Three-word phrases"])
        self.repeat_size.connect("notify::selected", lambda *_: self._render_repetitions())
        self.repeat_common = Gtk.CheckButton(label="Include everyday words (I, the, and…)")
        self.repeat_common.connect("toggled", lambda *_: self._render_repetitions())
        self.repeat_query = Gtk.Entry(placeholder_text="Or find a word / phrase…")
        self.repeat_query.connect("changed", lambda *_: self._render_repetitions())
        for control in (self.repeat_size, self.repeat_common, self.repeat_query):
            box.append(control)
        self.repeat_summary = self.label("Explore a passage to find returning sounds and words.")
        box.append(self.repeat_summary)
        self.repeat_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.append(self.repeat_list)

        page, box = self._craft_page("Mark the way you read a line. Click syllable marks to cycle soft → strong → secondary → unknown. Adjust counts and add pauses as you like.")
        pages.append(("My reading", page))
        self.reading_line = Gtk.DropDown.new_from_strings(["Choose a line"])
        self.reading_line.connect("notify::selected", self._select_reading)
        box.append(self.reading_line)
        self.reading_summary = self.label("Your choices change the rhythm hints, not your words.")
        box.append(self.reading_summary)
        self.reading_words = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.append(self.reading_words)
        reset = Gtk.Button(label="Return this line to dictionary hints")
        reset.connect("clicked", lambda *_: self._reset_reading())
        box.append(reset)

        page, box = self._craft_page("A few patterns to try aloud. Examples are references you can play with.")
        pages.append(("Reference cards", page))
        for title, pattern, example, hint in REFERENCE_CARDS:
            expander = Gtk.Expander(label=title)
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                              margin_start=8, margin_top=8, margin_bottom=12)
            content.append(self.label(pattern))
            content.append(self.label(example, css_classes=["monospace"]))
            content.append(self.label(hint))
            expander.set_child(content)
            box.append(expander)

        page, box = self._craft_page("Private notes for this document. Choose one question for this pass, and bookmark movements in the story.")
        pages.append(("My notes", page))
        self.focus_entry = Gtk.Entry(placeholder_text="This pass: what am I listening for?")
        self.focus_entry.connect("changed", self._notes_edited)
        box.append(self.focus_entry)
        self.craft_note = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR,
                                      top_margin=8, bottom_margin=8, left_margin=8, right_margin=8)
        self.craft_note.set_size_request(-1, 120)
        self.craft_note.get_buffer().connect("changed", self._notes_edited)
        box.append(self.craft_note)
        self.notes_status = self.label("Notes stay on this computer.", css_classes=["dim-label"])
        box.append(self.notes_status)
        retry = Gtk.Button(label="Save notes now")
        retry.connect("clicked", lambda *_: self.flush_craft_notes())
        box.append(retry)
        box.append(self.label("Section bookmarks", css_classes=["heading"]))
        self.bookmark_entry = Gtk.Entry(placeholder_text="A name for this movement…")
        box.append(self.bookmark_entry)
        bookmark = Gtk.Button(label="Bookmark the current editor line")
        bookmark.connect("clicked", lambda *_: self._bookmark())
        box.append(bookmark)
        self.bookmark_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.append(self.bookmark_list)
        return pages

    def _bind_craft(self, source, same_buffer):
        if source == (self._notes.source if self._notes else None):
            return
        self._flush_notes()
        previous = self._notes
        self._notes = None
        if source:
            from pathlib import Path
            source = str(Path(source).resolve())
            if source not in self._notes_cache:
                self._notes_cache[source] = CraftNotes(self._notes_directory, source,
                                                      initial=previous.data if same_buffer and previous else None)
            self._notes = self._notes_cache[source]
            if same_buffer and previous and any(previous.data.get(key) for key in
                                                ("focus", "note", "readings", "bookmarks", "pairs", "motifs")):
                self._notes.dirty = True
                self._flush_notes()
        self._loading_notes = True
        self.focus_entry.set_text(self._notes.data["focus"] if self._notes else "")
        self.craft_note.get_buffer().set_text(self._notes.data["note"] if self._notes else "", -1)
        self._loading_notes = False
        self.focus_entry.set_sensitive(self._notes is not None)
        self.craft_note.set_sensitive(self._notes is not None)
        self._repeat_group = None
        self.notes_status.set_label("Notes stay on this computer." if self._notes else "Open a document to keep craft notes.")

    def _live_text(self):
        return (self._buffer.get_text(self._buffer.get_start_iter(), self._buffer.get_end_iter(), False)
                if self._buffer else "")

    def _craft_current(self):
        return self._result is not None and self._snapshot == self._request and self._buffer is not None

    def _line_anchor(self, line):
        return anchor_at(self._live_text(), self._request[0] + line.start)

    def _line_record(self, line):
        return self._notes.reading(self._live_text(), self._request[0] + line.start) if self._notes else None

    def _personal_line(self, line):
        return apply_reading(line, self._line_record(line))

    def _line_marks(self, line):
        record = self._line_record(line)
        pauses = record.get("pauses", []) if record else []
        parts = []
        for index, word in enumerate(self._personal_line(line).words):
            parts.append(" ".join(STRESS_SYMBOLS[ch] for ch in word.stresses[0]))
            if index < len(pauses) and pauses[index] in ("|", "||"):
                parts.append(pauses[index])
        return "   ".join(parts)

    def _refresh_craft(self):
        self._render_map()
        self._render_repetitions()
        self._render_reading_selector()
        self._render_bookmarks()

    def _render_map(self):
        self._clear_children(self.map_list)
        if not self._craft_current():
            self.map_summary.set_label("Explore a passage to see its line endings.")
            return
        lines = self._result.lines[:self.MAX_LINES]
        titles = [f"L{line.number + self._request[1]} · {line.words[-1].text}" for line in lines]
        for selector in (self.pair_left, self.pair_right):
            old = selector.get_selected()
            selector.set_model(Gtk.StringList.new(titles or ["Choose a line"]))
            selector.set_selected(min(old, max(0, len(lines) - 1)))
        connections = {(pair.left, pair.right): pair.kind for pair in rhyme_connections(lines)}
        full = self._live_text()
        positions = {self._request[0] + line.start: index for index, line in enumerate(lines)}
        if self._notes:
            for pair in self._notes.data["pairs"]:
                left = positions.get(resolve_anchor(full, pair.get("left")))
                right = positions.get(resolve_anchor(full, pair.get("right")))
                if left is not None and right is not None and left != right:
                    connections[tuple(sorted((left, right)))] = "Your choice: " + str(pair.get("label", "Connection"))
        self.map_summary.set_label(f"{len(connections)} possible or chosen connection(s). Showing up to 80. Unpaired endings are welcome.")
        ordered = sorted(connections.items(), key=lambda item: (not item[1].startswith("Your choice:"), item[0]))
        for (left, right), kind in ordered[:80]:
            button = Gtk.Button(has_frame=False)
            button.set_child(self.label(f"{titles[left]} ↔ {titles[right]}\n{kind}"))
            button.connect("clicked", lambda _button, line=lines[left], request=self._request: self._go_to_line(line, request))
            self.map_list.append(button)
        unpaired = [titles[index] for index in range(len(lines)) if index not in {i for pair in connections for i in pair}]
        if unpaired:
            self.map_list.append(self.label("Unconnected endings: " + "; ".join(unpaired)))
        if self._notes and self._notes.data["pairs"]:
            clear = Gtk.Button(label="Clear my connection labels")
            clear.connect("clicked", lambda *_: self._clear_pairs())
            self.map_list.append(clear)

    def _remember_pair(self):
        if not self._craft_current() or not self._notes:
            return
        lines = self._result.lines[:self.MAX_LINES]
        left, right = self.pair_left.get_selected(), self.pair_right.get_selected()
        if left >= len(lines) or right >= len(lines) or left == right:
            self.toasts.add_toast(Adw.Toast.new("Choose two different lines."))
            return
        a, b = self._line_anchor(lines[left]), self._line_anchor(lines[right])
        full = self._live_text()
        starts = {self._request[0] + lines[left].start, self._request[0] + lines[right].start}
        pairs = self._notes.data["pairs"]
        pairs[:] = [pair for pair in pairs if {resolve_anchor(full, pair.get("left")),
                                              resolve_anchor(full, pair.get("right"))} != starts]
        pairs.append({"left": a, "right": b, "label": ["Rhyme", "Loose rhyme", "Intentional gap"][self.pair_kind.get_selected()]})
        self._save_craft()
        self._render_map()

    def _clear_pairs(self):
        if self._notes:
            self._notes.data["pairs"] = []
            self._save_craft()
            self._render_map()

    def _render_repetitions(self):
        if not hasattr(self, "repeat_list"):
            return
        self._clear_children(self.repeat_list)
        self._repeat_group = None
        if not self._craft_current():
            self.repeat_summary.set_label("Explore a passage to find returning words.")
            return
        groups = repetitions(self._request[2], self.repeat_size.get_selected() + 1,
                             self.repeat_common.get_active(), self.repeat_query.get_text())
        self.repeat_summary.set_label(f"{len(groups)} returning word / phrase group(s). Showing up to 40.")
        motifs = {record.get("phrase") for record in self._notes.data["motifs"]} if self._notes else set()
        for group in groups[:40]:
            expander = Gtk.Expander(label=f"{group.phrase} · {len(group.spans)} occurrence(s)" + (" · motif" if group.phrase in motifs else ""))
            contents = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5, margin_start=8, margin_top=6)
            highlight = Gtk.Button(label="Highlight these occurrences")
            highlight.connect("clicked", lambda _button, item=group, request=self._request: self._show_repetition(item, request))
            contents.append(highlight)
            remember = Gtk.CheckButton(label="Remember as a motif", active=group.phrase in motifs)
            remember.connect("toggled", lambda control, phrase=group.phrase, current=self._request: self._remember_motif(phrase, control.get_active(), current))
            contents.append(remember)
            for start, end in group.spans[:100]:
                sample = self._request[2]
                line_start, line_end = sample.rfind("\n", 0, start) + 1, sample.find("\n", end)
                excerpt = sample[line_start:line_end if line_end >= 0 else len(sample)]
                number = self._request[1] + sample.count("\n", 0, start) + 1
                button = Gtk.Button(has_frame=False)
                button.set_child(self.label(f"L{number}: {excerpt[:160]}"))
                button.connect("clicked", lambda _button, offset=start, request=self._request: self._go_to_offset(offset, request))
                contents.append(button)
            expander.set_child(contents)
            self.repeat_list.append(expander)
        self._apply_colors()

    def _go_to_offset(self, offset, request):
        if request != self._snapshot or not self._buffer:
            return
        iterator = self._buffer.get_iter_at_offset(request[0] + offset)
        self._buffer.place_cursor(iterator)
        self._view.scroll_to_iter(iterator, .15, False, 0, 0)
        self._view.grab_focus()

    def _show_repetition(self, group, request):
        if request == self._snapshot:
            self._repeat_group = group
            self._apply_colors()

    def _remember_motif(self, phrase, enabled, request):
        if self._notes and request == self._snapshot and self._craft_current():
            motifs = self._notes.data["motifs"]
            motifs[:] = [record for record in motifs if record.get("phrase") != phrase]
            if enabled:
                motifs.append({"phrase": phrase})
            self._save_craft()

    def _render_reading_selector(self):
        self._reading_updating = True
        lines = self._result.lines[:self.MAX_LINES] if self._craft_current() else ()
        self.reading_line.set_model(Gtk.StringList.new([f"L{line.number + self._request[1]} · {line.text[:70]}" for line in lines]
                                                      or ["Choose a line"]))
        self._reading_index = min(self._reading_index, max(0, len(lines) - 1))
        self.reading_line.set_selected(self._reading_index)
        self._reading_updating = False
        self._render_reading()

    def _select_reading(self, *_args):
        if not self._reading_updating:
            self._reading_index = self.reading_line.get_selected()
            self._render_reading()

    def _selected_reading(self):
        if not self._craft_current() or self._reading_index >= min(len(self._result.lines), self.MAX_LINES):
            return None
        line = self._result.lines[self._reading_index]
        start = self._request[0] + line.start
        full = self._live_text()
        actual = next((item for item in line_locations(full) if item[1] == start), None)
        if actual is None or self._request[0] + line.end != start + len(actual[2]):
            return None
        return line

    def _render_reading(self):
        self._clear_children(self.reading_words)
        line = self._selected_reading()
        if line is None:
            self.reading_summary.set_label("Explore a passage and choose a complete line to save your reading.")
            return
        personal = self._personal_line(line)
        status = ("Your reading has unsaved private notes." if self._notes and self._notes.dirty else
                  "Your reading is saved privately.")
        self.reading_summary.set_label(f"{personal.syllables} syllables · " + self._line_marks(line)
                                       + ("\n" + status if self._line_record(line) else "\nStarting from dictionary hints."))
        record = self._line_record(line) or {}
        pauses = record.get("pauses", [])
        for index, word in enumerate(personal.words[:60]):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            head = Gtk.Box(spacing=8)
            head.append(self.label(word.text, hexpand=True, css_classes=["heading"]))
            count = Gtk.SpinButton.new_with_range(1, 20, 1)
            count.set_value(len(word.stresses[0]))
            count.set_tooltip_text("Syllables in your reading")
            count.connect("value-changed", lambda control, item=index, current=self._request, target=line.start: self._change_reading(item, "count", int(control.get_value()), current, target))
            head.append(count)
            box.append(head)
            marks = self._flow()
            for syllable, value in enumerate(word.stresses[0]):
                button = Gtk.Button(label=STRESS_SYMBOLS[value])
                button.set_tooltip_text("Cycle this syllable's stress")
                button.connect("clicked", lambda _button, item=index, beat=syllable, current=self._request, target=line.start: self._change_reading(item, "beat", beat, current, target))
                marks.append(button)
            box.append(marks)
            pause = Gtk.DropDown.new_from_strings(["No pause after this word", "Short pause |", "Long pause ||"])
            value = pauses[index] if index < len(pauses) and pauses[index] in ("", "|", "||") else ""
            pause.set_selected(["", "|", "||"].index(value))
            pause.connect("notify::selected", lambda control, item=index, current=self._request, target=line.start: self._change_reading(item, "pause", control.get_selected(), current, target))
            box.append(pause)
            self.reading_words.append(box)
        if len(personal.words) > 60:
            self.reading_words.append(self.label("Showing 60 words. Select a shorter passage to mark more."))

    def _change_reading(self, index, kind, value, request, target=None):
        line = self._selected_reading()
        if line is None or not self._notes or request != self._snapshot:
            return
        if target is not None and line.start != target:
            return
        personal = self._personal_line(line)
        if index >= len(personal.words):
            return
        previous = self._line_record(line) or {}
        stresses = [word.stresses[0] for word in personal.words]
        custom = list(previous.get("custom", [False] * len(stresses)))
        if len(custom) != len(stresses):
            custom = [False] * len(stresses)
        pauses = list(previous.get("pauses", [""] * len(stresses)))
        if len(pauses) != len(stresses):
            pauses = [""] * len(stresses)
        if kind == "count":
            stresses[index] = (stresses[index] + "?" * value)[:value]
            custom[index] = True
        elif kind == "beat":
            if value >= len(stresses[index]):
                return
            old = stresses[index][value]
            new = "012?"[("012?".index(old) + 1) % 4]
            stresses[index] = stresses[index][:value] + new + stresses[index][value + 1:]
            custom[index] = True
        else:
            pauses[index] = ["", "|", "||"][value]
        self._notes.set_reading(self._live_text(), request[0] + line.start,
                                {"words": [word.text for word in line.words], "stresses": stresses,
                                 "custom": custom, "pauses": pauses})
        self._save_craft()
        self._render_reading()
        self._render_line_rows()
        self._apply_colors()

    def _reset_reading(self):
        line = self._selected_reading()
        if line is not None and self._notes:
            self._notes.set_reading(self._live_text(), self._request[0] + line.start, None)
            self._save_craft()
            self._render_reading()
            self._render_line_rows()
            self._apply_colors()

    def _notes_edited(self, *_args):
        if self._loading_notes or not self._notes:
            return
        self._notes.data["focus"] = self.focus_entry.get_text()
        buffer = self.craft_note.get_buffer()
        self._notes.data["note"] = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)
        self._notes.dirty = True
        self.notes_status.set_label("Saving private notes…")
        if self._notes_timer is not None:
            GLib.source_remove(self._notes_timer)
        self._notes_timer = GLib.timeout_add(500, self._flush_notes)

    def _save_craft(self):
        self._notes.dirty = True
        self._flush_notes()

    def _flush_notes(self):
        if self._notes_timer is not None:
            GLib.source_remove(self._notes_timer)
            self._notes_timer = None
        if self._notes and self._notes.dirty:
            try:
                self._notes.save()
            except OSError:
                self.notes_status.set_label("Could not save notes. Your manuscript is safe; use Save notes now to retry.")
                return False
            self.notes_status.set_label("Saved privately on this computer.")
        return False

    def flush_craft_notes(self):
        self._flush_notes()
        failed = False
        for notes in self._notes_cache.values():
            if notes.dirty:
                try:
                    notes.save()
                except OSError:
                    failed = True
        if failed:
            self.notes_status.set_label("Some private notes could not be saved. Use Save notes now to retry.")
            self.toasts.add_toast(Adw.Toast.new("Craft notes could not be saved. Keep this window open and retry."))
        return not failed

    def _bookmark(self):
        if not self._notes or not self._buffer:
            return
        label = self.bookmark_entry.get_text().strip()
        if not label:
            self.toasts.add_toast(Adw.Toast.new("Give this movement a name first."))
            return
        cursor = self._buffer.get_iter_at_mark(self._buffer.get_insert()).get_offset()
        self._notes.data["bookmarks"].append({"label": label, "anchor": anchor_at(self._live_text(), cursor)})
        self.bookmark_entry.set_text("")
        self._save_craft()
        self._render_bookmarks()

    def _render_bookmarks(self):
        self._clear_children(self.bookmark_list)
        if not self._notes:
            return
        text = self._live_text()
        stale = sum(resolve_anchor(text, record.get("anchor")) is None for record in self._notes.data["readings"])
        if stale:
            self.bookmark_list.append(self.label(f"{stale} saved reading(s) have changed or ambiguous lines; those marks are kept aside."))
        stale_pairs = sum(resolve_anchor(text, record.get("left")) is None or resolve_anchor(text, record.get("right")) is None
                          for record in self._notes.data["pairs"])
        if stale_pairs:
            self.bookmark_list.append(self.label(f"{stale_pairs} connection label(s) have changed or ambiguous lines and are kept aside."))
        for record in self._notes.data["bookmarks"]:
            offset = resolve_anchor(text, record.get("anchor"))
            row = Gtk.Box(spacing=6)
            button = Gtk.Button(hexpand=True)
            button.set_child(self.label(str(record.get("label", "Section")) + (" · anchor changed" if offset is None else "")))
            button.set_sensitive(offset is not None)
            button.connect("clicked", lambda _button, item=record: self._visit_bookmark(item))
            row.append(button)
            remove = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text="Remove bookmark")
            remove.connect("clicked", lambda _button, item=record: self._remove_bookmark(item))
            row.append(remove)
            self.bookmark_list.append(row)

    def _visit_bookmark(self, record):
        if self._buffer:
            offset = resolve_anchor(self._live_text(), record.get("anchor"))
            if offset is not None:
                iterator = self._buffer.get_iter_at_offset(offset)
                self._buffer.place_cursor(iterator)
                self._view.scroll_to_iter(iterator, .15, False, 0, 0)
                self._view.grab_focus()

    def _remove_bookmark(self, record):
        if self._notes and record in self._notes.data["bookmarks"]:
            self._notes.data["bookmarks"].remove(record)
            self._save_craft()
            self._render_bookmarks()
