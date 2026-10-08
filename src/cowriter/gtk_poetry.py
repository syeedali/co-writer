"""A small, nonmodal poetry workbench that decorates the active editor."""

import re
import threading

from gi.repository import Adw, Gdk, GLib, Gtk, Pango

from .poetry import WORDS, analyze, dictionary
from .gtk_craft import CraftToolsMixin


class LatestWorker:
    """Keep one running job and only the newest pending request."""

    def __init__(self, function, callback):
        self.function, self.callback = function, callback
        self.generation = 0
        self.running = False
        self.pending = None
        self.closed = False

    def invalidate(self):
        self.generation += 1
        self.pending = None

    def submit(self, request):
        self.invalidate()
        job = (self.generation, request)
        if self.running:
            self.pending = job
        else:
            self._launch(job)

    def _launch(self, job):
        self.running = True
        generation, request = job

        def work():
            try:
                result, error = self.function(request), None
            except Exception as exc:
                result, error = None, str(exc)
            GLib.idle_add(self._finish, generation, request, result, error)

        threading.Thread(target=work, daemon=True, name="cowriter-poetry").start()

    def _finish(self, generation, request, result, error):
        self.running = False
        if self.closed:
            return False
        if generation == self.generation:
            self.callback(request, result, error)
        pending, self.pending = self.pending, None
        if pending:
            self._launch(pending)
        return False

    def close(self):
        self.closed = True
        self.invalidate()


class PoetryTools(CraftToolsMixin, Adw.Window):
    MAX_CHARACTERS = 24000
    MAX_LINES = 100
    RHYME_COLORS = ("#c18aff", "#62c6a5", "#eda866", "#7db7f0", "#e482b8", "#c7c76e")

    def __init__(self, owner, notes_directory):
        super().__init__(title="Poetry & prose", transient_for=owner,
                         modal=False, destroy_with_parent=True)
        self.owner = owner
        self._init_craft(notes_directory)
        self.set_default_size(540, 700)
        self.set_size_request(360, 420)
        self._closed = False
        self._view = self._buffer = None
        self._handlers = []
        self._tags = {}
        self._timer = self._rhyme_timer = None
        self._snapshot = None
        self._result = None
        self._request = None
        self._passage_generation = 0
        self._analysis = LatestWorker(lambda request: analyze(request[2]), self._analyzed)
        self._rhymes = LatestWorker(lambda request: dictionary().find_rhymes(request[0], syllables=request[1]), self._rhymed)
        self._build()
        self.connect("close-request", self._closing)
        self.connect("destroy", self._closing)
        self.bind_active()

    @staticmethod
    def label(text, **kwargs):
        return Gtk.Label(label=text, xalign=0, wrap=True, **kwargs)

    def _build(self):
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        self.toasts = Adw.ToastOverlay()
        self.toasts.set_child(toolbar)
        self.set_content(self.toasts)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                      margin_start=14, margin_end=14, margin_top=8, margin_bottom=14)
        toolbar.set_content(box)
        box.append(self.label("A few ways to listen to your words.", css_classes=["heading"]))
        box.append(self.label("English sound hints, not rules. Your ear gets the final say."))
        controls = Gtk.Box(spacing=12)
        self.rhythm_colors = Gtk.CheckButton(label="Rhythm colors")
        self.rhythm_colors.set_tooltip_text("Shade words by dictionary stress: soft, strong, mixed, or unknown. Hover a word for its possible readings.")
        self.rhyme_colors = Gtk.CheckButton(label="Rhyme colors", active=True)
        self.rhyme_colors.set_tooltip_text("Give matching line-ending sounds the same color. Repeated identical words alone are not treated as rhymes.")
        for control in (self.rhythm_colors, self.rhyme_colors):
            control.connect("toggled", lambda *_: self._apply_colors())
            controls.append(control)
        box.append(controls)
        self.color_legend = self.label("Green: soft · Amber: strong · Violet: mixed · Gray: unknown / estimated",
                                       visible=False, css_classes=["dim-label"])
        self.rhythm_colors.connect("toggled", lambda control: self.color_legend.set_visible(control.get_active()))
        box.append(self.color_legend)

        tabs = Gtk.Stack(hexpand=True, vexpand=True)
        self.tool_choice = Gtk.DropDown.new_from_strings(["Rhythm & lines", "Find rhymes", "Rhyme map", "Repetitions", "My reading", "Reference cards", "My notes"])
        self.tool_choice.connect("notify::selected", lambda control, *_: tabs.set_visible_child_name(str(control.get_selected())))
        box.append(self.tool_choice)
        self.scope = Gtk.DropDown.new_from_strings(["Current stanza / paragraph", "Selected text", "Whole document"])
        self.scope.set_tooltip_text("Passage used by rhythm hints, the rhyme map, repetitions, and your reading")
        self.scope.connect("notify::selected", self._scope_changed)
        box.append(self.scope)
        box.append(tabs)
        rhythm = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                         margin_start=10, margin_end=10, margin_top=10, margin_bottom=10)
        tabs.add_named(rhythm, "0")
        self.summary = self.label("Open a document to explore its sound.")
        rhythm.append(self.summary)
        rhythm.append(self.label("· soft    ● strong    ◐ secondary    ? estimated", css_classes=["dim-label"]))
        rhythm.append(self.label("Dictionary stress is one possible reading. Speech, dialect and emphasis can change it.", css_classes=["dim-label"]))
        self.line_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.line_list.add_css_class("boxed-list")
        scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(self.line_list)
        rhythm.append(scroll)

        rhymes = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                         margin_start=10, margin_end=10, margin_top=10, margin_bottom=10)
        tabs.add_named(rhymes, "1")
        rhymes.append(self.label("Find a word with a sound you like."))
        self.rhyme_entry = Gtk.Entry(placeholder_text="A word to rhyme with…", hexpand=True)
        self.rhyme_entry.connect("changed", self._queue_rhyme)
        self.rhyme_entry.connect("activate", lambda *_: self._find_rhymes())
        rhymes.append(self.rhyme_entry)
        self.rhyme_syllables = Gtk.DropDown.new_from_strings(["Any syllable count"] +
                                                           [f"{number} syllable" + ("s" if number != 1 else "") for number in range(1, 9)])
        self.rhyme_syllables.connect("notify::selected", self._queue_rhyme)
        rhymes.append(self.rhyme_syllables)
        use_word = Gtk.Button(label="Use word at cursor / selection")
        use_word.connect("clicked", lambda *_: self.use_editor_word())
        rhymes.append(use_word)
        self.rhyme_status = self.label("Lookups stay on this computer. Click a result to copy it.")
        rhymes.append(self.rhyme_status)
        results = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        results.append(self.label("Rhymes", css_classes=["heading"]))
        self.exact_words = self._flow()
        results.append(self.exact_words)
        results.append(self.label("Vowel echoes", css_classes=["heading"]))
        results.append(self.label("Similar vowel sounds with different endings—looser possibilities.", css_classes=["dim-label"]))
        self.echo_words = self._flow()
        results.append(self.echo_words)
        scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(results)
        rhymes.append(scroll)
        rhymes.append(self.label("From the local CMU English pronunciation dictionary; results can include names and uncommon words.", css_classes=["dim-label"]))
        for index, (_name, page) in enumerate(self._build_craft(), 2):
            tabs.add_named(page, str(index))

    @staticmethod
    def _flow():
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=False,
                           row_spacing=5, column_spacing=5, min_children_per_line=1,
                           max_children_per_line=5)
        return flow

    def bind_active(self):
        if self._closed:
            return
        page, view, buffer = self.owner._get_current_page()
        source = self.owner.open_tabs.get(page)
        self._bind_craft(source, buffer is self._buffer)
        if buffer is self._buffer:
            return
        self._passage_generation += 1
        self._unbind()
        self._view, self._buffer = view, buffer
        self._snapshot = None
        self._result = None
        self._analysis.invalidate()
        if buffer:
            for name, color in (("soft", "#62c6a5"), ("strong", "#eda866"),
                                ("mixed", "#c18aff"), ("unknown", "#999999")):
                self._add_tag("poetry-" + name, color, .16)
            for index, color in enumerate(self.RHYME_COLORS):
                self._add_tag("poetry-rhyme-" + str(index), color, .28)
            self._add_tag("poetry-repeat", "#ebcd55", .35)
            self._handlers = [(buffer, buffer.connect("changed", self._changed)),
                              (buffer, buffer.connect("mark-set", self._moved)),
                              (view, view.connect("query-tooltip", self._tooltip))]
        self._queue()

    def _add_tag(self, name, color, alpha):
        tag = self._buffer.get_tag_table().lookup(name)
        if tag is None:
            rgba = Gdk.RGBA()
            rgba.parse(color)
            rgba.alpha = alpha
            tag = self._buffer.create_tag(name, background_rgba=rgba)
        self._tags[name] = tag

    def _unbind(self):
        self._clear_colors()
        for obj, handler in self._handlers:
            obj.disconnect(handler)
        self._handlers = []
        self._tags = {}
        self._view = self._buffer = None

    def _changed(self, *_args):
        self._passage_generation += 1
        self._repeat_group = None
        self._analysis.invalidate()
        self._result = None
        self._snapshot = None
        self._clear_colors()
        self._clear_children(self.line_list)
        self.summary.set_label("Listening…")
        self._queue()

    def _moved(self, _buffer, _iterator, mark):
        if mark.get_name() in ("insert", "selection_bound"):
            self._queue()

    def _scope_changed(self, *_args):
        self._passage_generation += 1
        self._repeat_group = None
        self._snapshot = None
        self._analysis.invalidate()
        self._result = None
        self._clear_colors()
        self._queue()

    def _queue(self):
        if self._timer is not None:
            GLib.source_remove(self._timer)
        self._timer = GLib.timeout_add(350, self._start)

    def _start(self):
        self._timer = None
        if self._closed:
            return False
        if not self._buffer:
            self.summary.set_label("Open a document to explore its sound.")
            self._clear_children(self.line_list)
            self._refresh_craft()
            return False
        buffer = self._buffer
        text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)
        start, end = 0, len(text)
        scope = self.scope.get_selected()
        if scope == 1:
            bounds = buffer.get_selection_bounds()
            if not bounds:
                self._analysis.invalidate()
                self._result = self._snapshot = None
                self._clear_colors()
                self._clear_children(self.line_list)
                self.summary.set_label("Select a passage in the editor to explore it.")
                self._refresh_craft()
                return False
            start, end = (iterator.get_offset() for iterator in bounds)
        elif scope == 0:
            cursor = buffer.get_iter_at_mark(buffer.get_insert()).get_offset()
            for separator in re.finditer(r"\n[ \t]*\n", text):
                if separator.end() <= cursor:
                    start = separator.end()
                elif separator.start() >= cursor:
                    end = separator.start()
                    break
        clipped = end - start > self.MAX_CHARACTERS
        end = min(end, start + self.MAX_CHARACTERS)
        sample = text[start:end]
        request = (start, text.count("\n", 0, start), sample, clipped, scope, self._passage_generation)
        if request == self._snapshot:
            return False
        self._snapshot = request
        self._result = None
        self._clear_colors()
        self._clear_children(self.line_list)
        self.summary.set_label("Listening…")
        self._analysis.submit(request)
        return False

    def _analyzed(self, request, result, error):
        if self._closed:
            return
        if error:
            self.summary.set_label("Sound tools are unavailable. Reopen this window to try again.")
            self._snapshot = None
            return
        self._result, self._request = result, request
        self._render_line_rows()
        self._refresh_craft()
        self._apply_colors()

    def _render_line_rows(self):
        if not self._result:
            return
        request, result = self._request, self._result
        self._clear_children(self.line_list)
        lines = result.lines[:self.MAX_LINES]
        unknown = sum(word.guessed for line in lines for word in self._personal_line(line).words)
        label = f"{len(lines)} line" + ("s" if len(lines) != 1 else "")
        if unknown:
            label += f" · {unknown} word" + ("s" if unknown != 1 else "") + " estimated"
        if request[3] or len(result.lines) > self.MAX_LINES:
            label += " · Showing an excerpt; select a shorter passage to explore more."
        self.summary.set_label(label if lines else "No words to explore in this passage.")
        for line in lines:
            personal = self._personal_line(line)
            row = Gtk.ListBoxRow(activatable=False)
            button = Gtk.Button(has_frame=False, hexpand=True)
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5,
                              margin_top=6, margin_bottom=6)
            ending = ""
            if line.rhyme_group >= 0:
                ending = f" · rhyme {line.rhyme_group + 1}"
            content.append(self.label(f"Line {line.number + request[1]} · {personal.syllables} syllables{ending}",
                                      css_classes=["heading"]))
            content.append(self.label(line.text, ellipsize=Pango.EllipsizeMode.END, lines=2))
            marks = self.label(self._line_marks(line))
            marks.add_css_class("monospace")
            content.append(marks)
            button.set_child(content)
            button.set_tooltip_text("Go to this line. Hover words in the editor for alternate readings.")
            button.connect("clicked", lambda _button, item=line, current=request: self._go_to_line(item, current))
            row.set_child(button)
            self.line_list.append(row)
        self._apply_colors()

    def _go_to_line(self, line, request):
        if request != self._snapshot or not self._buffer:
            return
        iterator = self._buffer.get_iter_at_offset(request[0] + line.start)
        self._buffer.place_cursor(iterator)
        self._view.scroll_to_iter(iterator, .15, False, 0, 0)
        self._view.grab_focus()

    def _clear_colors(self):
        if self._buffer:
            for tag in self._tags.values():
                self._buffer.remove_tag(tag, self._buffer.get_start_iter(), self._buffer.get_end_iter())

    def _apply_colors(self):
        self._clear_colors()
        if not self._buffer or not self._result:
            return
        base = self._request[0]
        for line in self._result.lines[:self.MAX_LINES]:
            personal = self._personal_line(line)
            if self.rhythm_colors.get_active():
                for word in personal.words:
                    stress = set(word.stresses[0])
                    kind = ("unknown" if word.guessed or "?" in stress else "soft" if stress == {"0"} else
                            "strong" if "0" not in stress else "mixed")
                    self._apply_tag("poetry-" + kind, base + word.start, base + word.end)
            if self.rhyme_colors.get_active() and line.rhyme_group >= 0:
                word = line.words[-1]
                self._apply_tag("poetry-rhyme-" + str(line.rhyme_group % len(self.RHYME_COLORS)),
                                base + word.start, base + word.end)
        if self._repeat_group:
            for start, end in self._repeat_group.spans:
                self._apply_tag("poetry-repeat", base + start, base + end)

    def _apply_tag(self, name, start, end):
        self._buffer.apply_tag(self._tags[name], self._buffer.get_iter_at_offset(start),
                               self._buffer.get_iter_at_offset(end))

    def _tooltip(self, view, x, y, keyboard, tooltip):
        if not self._result:
            return False
        if keyboard:
            iterator = self._buffer.get_iter_at_mark(self._buffer.get_insert())
        else:
            bx, by = view.window_to_buffer_coords(Gtk.TextWindowType.WIDGET, x, y)
            found, iterator = view.get_iter_at_location(bx, by)
            if not found:
                return False
        offset = iterator.get_offset() - self._request[0]
        for line in self._result.lines[:self.MAX_LINES]:
            for word in self._personal_line(line).words:
                if word.start <= offset < word.end:
                    count = str(word.minimum) if word.minimum == word.maximum else f"{word.minimum}–{word.maximum}"
                    hint = ("This line includes your reading marks." if self._line_record(line) else
                            "Estimated syllables; stress unknown." if word.guessed else
                            "Possible dictionary readings; your emphasis may differ.")
                    tooltip.set_text(f"{word.text} · {count} syllables\n{word.rhythm}\n{hint}")
                    return True
        return False

    @staticmethod
    def _clear_children(container):
        child = container.get_first_child()
        while child:
            following = child.get_next_sibling()
            container.remove(child)
            child = following

    def _queue_rhyme(self, *_args):
        self._rhymes.invalidate()
        if self._rhyme_timer is not None:
            GLib.source_remove(self._rhyme_timer)
        self._clear_children(self.exact_words)
        self._clear_children(self.echo_words)
        self.rhyme_status.set_label("Looking for sounds…")
        self._rhyme_timer = GLib.timeout_add(300, self._find_rhymes)

    def _find_rhymes(self):
        if self._rhyme_timer is not None:
            GLib.source_remove(self._rhyme_timer)
            self._rhyme_timer = None
        if self._closed:
            return False
        word = self.rhyme_entry.get_text().strip()
        if not WORDS.fullmatch(word):
            self.rhyme_status.set_label("Enter one word, or use a word from your editor.")
            return False
        self._rhymes.submit((word, self.rhyme_syllables.get_selected() or None))
        return False

    def _rhymed(self, request, result, error):
        word, syllables = request
        if error:
            self.rhyme_status.set_label("The local rhyme dictionary is unavailable. Reopen this window to try again.")
            return
        self._clear_children(self.exact_words)
        self._clear_children(self.echo_words)
        if not result.known:
            self.rhyme_status.set_label(f"“{word}” is not in the dictionary yet. Try another word or spelling.")
            return
        filter_hint = f" · {syllables} syllable(s)" if syllables else ""
        self.rhyme_status.set_label(f"Sounds for “{word}”{filter_hint} · up to 60 per group. Click a word to copy it.")
        for flow, words in ((self.exact_words, result.exact), (self.echo_words, result.echoes)):
            if not words:
                flow.append(self.label("No matches in this dictionary."))
            for candidate in words:
                button = Gtk.Button(label=candidate, tooltip_text=f"Copy “{candidate}”")
                button.connect("clicked", lambda _button, value=candidate: self._copy_word(value))
                flow.append(button)

    def _copy_word(self, word):
        self.get_clipboard().set(word)
        self.toasts.add_toast(Adw.Toast.new(f"Copied “{word}”"))

    def use_editor_word(self):
        if not self._buffer:
            self.rhyme_status.set_label("Open a document or type a word above.")
            return
        buffer = self._buffer
        bounds = buffer.get_selection_bounds()
        if bounds:
            word = buffer.get_text(bounds[0], bounds[1], False).strip()
            if WORDS.fullmatch(word):
                self.rhyme_entry.set_text(word)
                return
            self.rhyme_status.set_label("Select one word to look up its sounds.")
            return
        text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)
        cursor = buffer.get_iter_at_mark(buffer.get_insert()).get_offset()
        match = next((word for word in WORDS.finditer(text) if word.start() <= cursor < word.end()), None)
        if match is None:
            match = next((word for word in WORDS.finditer(text) if word.end() == cursor), None)
        if match:
            self.rhyme_entry.set_text(match[0])
        else:
            self.rhyme_status.set_label("Place the cursor on a word, or type one above.")

    def _closing(self, *_args):
        if self._closed:
            return False
        saved = self.flush_craft_notes()
        if not saved and not getattr(self, "_force_close", False) and not self.owner._disposed:
            return True
        self._closed = True
        for timer in (self._timer, self._rhyme_timer):
            if timer is not None:
                GLib.source_remove(timer)
        self._timer = self._rhyme_timer = None
        self._analysis.close()
        self._rhymes.close()
        self._unbind()
        if self.owner._poetry_tools is self:
            self.owner._poetry_tools = None
        return False

    def destroy(self):
        self._force_close = True
        self._closing()
        super().destroy()
