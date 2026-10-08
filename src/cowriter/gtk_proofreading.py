"""Debounced proofreading decorations and explicit corrections for GTK editors."""

import threading

from gi.repository import Gdk, GLib, Gtk, Pango

from .proofreading import CheckResult, check_text


class EditorProofreading:
    def __init__(self, view, on_status, on_learn, ignored=(), enabled=True):
        self.view = view
        self.buffer = view.get_buffer()
        self.on_status = on_status
        self.on_learn = on_learn
        self.ignored = set(ignored)
        self.enabled = enabled
        self.issues = ()
        self.warning = ""
        self.checking = False
        self._closed = False
        self._generation = 0
        self._timeout = None
        self._running = False
        self._pending = None
        self._popover = None
        self._tags = {}
        for kind, color in (("spelling", "#ed6262"), ("grammar", "#62a8ed")):
            rgba = Gdk.RGBA()
            rgba.parse(color)
            self._tags[kind] = self.buffer.create_tag(
                "proofreading-" + kind, underline=Pango.Underline.ERROR, underline_rgba=rgba)
        self._changed_handler = self.buffer.connect("changed", self._changed)
        view.set_has_tooltip(True)
        self._tooltip_handler = view.connect("query-tooltip", self._tooltip)
        click = Gtk.GestureClick(button=1)
        click.connect("released", self._clicked)
        view.add_controller(click)
        self._click = click
        self._changed()

    def _clear(self):
        self.issues = ()
        for tag in self._tags.values():
            self.buffer.remove_tag(tag, self.buffer.get_start_iter(), self.buffer.get_end_iter())
        self._close_popover()

    def _changed(self, *_args):
        if self._closed:
            return
        self._generation += 1
        if self._timeout is not None:
            GLib.source_remove(self._timeout)
            self._timeout = None
        self._pending = None
        self._clear()
        self.checking = self.enabled
        if self.enabled:
            self._timeout = GLib.timeout_add(450, self._start)
        self.on_status()

    def _start(self):
        self._timeout = None
        if self._closed or not self.enabled:
            return False
        text = self.buffer.get_text(self.buffer.get_start_iter(), self.buffer.get_end_iter(), False)
        snapshot = (self._generation, text, tuple(self.ignored))
        if self._running:
            # At most one worker per editor; only retain the latest request.
            self._pending = snapshot
        else:
            self._launch(snapshot)
        return False

    def _launch(self, snapshot):
        self._running = True
        generation, text, ignored = snapshot

        def worker():
            try:
                result = check_text(text, ignored=ignored)
            except Exception:
                # Keep an unexpected checker failure out of the writing path.
                result = CheckResult((), "Proofreading unavailable. Try toggling Spelling & grammar off and on.")
            GLib.idle_add(self._finish, generation, result)

        threading.Thread(target=worker, daemon=True, name="cowriter-proofreading").start()

    def _finish(self, generation, result):
        self._running = False
        if self._closed:
            return False
        if self.enabled and generation == self._generation:
            self.issues = result.issues
            self.warning = result.warning
            self.checking = False
            for issue in self.issues:
                self.buffer.apply_tag(self._tags[issue.kind],
                                      self.buffer.get_iter_at_offset(issue.start),
                                      self.buffer.get_iter_at_offset(issue.end))
            self.on_status()
        pending, self._pending = self._pending, None
        if pending and self.enabled and pending[0] == self._generation:
            self._launch(pending)
        return False

    def set_enabled(self, enabled):
        self.enabled = enabled
        self._changed()

    def set_ignored(self, words):
        self.ignored = set(words)
        self._changed()

    def _issue_at(self, offset):
        return next((issue for issue in self.issues if issue.start <= offset < issue.end), None)

    def _iter_at(self, x, y):
        bx, by = self.view.window_to_buffer_coords(Gtk.TextWindowType.WIDGET, int(x), int(y))
        found, iterator = self.view.get_iter_at_location(bx, by)
        return iterator if found else None

    def _tooltip(self, _view, x, y, keyboard, tooltip):
        iterator = (self.buffer.get_iter_at_mark(self.buffer.get_insert()) if keyboard
                    else self._iter_at(x, y))
        issue = self._issue_at(iterator.get_offset()) if iterator else None
        if not issue:
            return False
        suggestion = " Suggestion: " + issue.suggestions[0] + "." if issue.suggestions else ""
        tooltip.set_text(issue.message + suggestion + " Click the underline for options, or press F7.")
        return True

    def _clicked(self, _gesture, presses, x, y):
        if presses != 1 or self.buffer.get_has_selection():
            return
        iterator = self._iter_at(x, y)
        issue = self._issue_at(iterator.get_offset()) if iterator else None
        if issue:
            self.show_issue(issue)

    def _close_popover(self):
        if self._popover:
            self._popover.popdown()
            self._popover.unparent()
            self._popover = None

    def show_issue(self, issue):
        if issue not in self.issues or self._closed:
            return
        self._close_popover()
        popover = Gtk.Popover()
        popover.set_parent(self.view)
        popover.set_autohide(True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                      margin_start=8, margin_end=8, margin_top=8, margin_bottom=8)
        label = Gtk.Label(label=issue.message, wrap=True, max_width_chars=32, xalign=0)
        box.append(label)
        generation = self._generation
        for suggestion in issue.suggestions:
            button = Gtk.Button(label=suggestion)
            button.connect("clicked", lambda _button, value=suggestion:
                           self.replace(issue, value, generation))
            box.append(button)
        word = self.buffer.get_text(self.buffer.get_iter_at_offset(issue.start),
                                    self.buffer.get_iter_at_offset(issue.end), False)
        ignore = Gtk.Button(label="Ignore in this document")
        ignore.connect("clicked", lambda *_: self.set_ignored(self.ignored | {word}))
        box.append(ignore)
        if issue.kind == "spelling":
            learn = Gtk.Button(label="Add to personal dictionary")
            learn.connect("clicked", lambda *_: self.on_learn(word))
            box.append(learn)
        popover.set_child(box)
        location = self.view.get_iter_location(self.buffer.get_iter_at_offset(issue.start))
        location.x, location.y = self.view.buffer_to_window_coords(
            Gtk.TextWindowType.WIDGET, location.x, location.y)
        popover.set_pointing_to(location)
        self._popover = popover
        popover.popup()

    def replace(self, issue, replacement, generation):
        # A popup or delayed callback must never edit a newer document revision.
        if self._closed or generation != self._generation or issue not in self.issues:
            return
        self.buffer.begin_user_action()
        try:
            self.buffer.delete(self.buffer.get_iter_at_offset(issue.start),
                               self.buffer.get_iter_at_offset(issue.end))
            self.buffer.insert(self.buffer.get_iter_at_offset(issue.start), replacement, -1)
        finally:
            self.buffer.end_user_action()
        self.view.grab_focus()

    def next_issue(self):
        if not self.issues:
            return
        offset = self.buffer.get_iter_at_mark(self.buffer.get_insert()).get_offset()
        issue = next((item for item in self.issues if item.start > offset), self.issues[0])
        self.buffer.place_cursor(self.buffer.get_iter_at_offset(issue.start))
        self.view.scroll_to_iter(self.buffer.get_iter_at_offset(issue.start), 0.15, False, 0, 0)
        self.show_issue(issue)

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._pending = None
        if self._timeout is not None:
            GLib.source_remove(self._timeout)
            self._timeout = None
        self._clear()
        self.buffer.disconnect(self._changed_handler)
        self.view.disconnect(self._tooltip_handler)
        self.view.remove_controller(self._click)
