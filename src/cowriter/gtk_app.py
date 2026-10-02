"""Co-Writer — GTK4 + libadwaita native GNOME application."""

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
try:
    gi.require_version("GtkSource", "5")
    from gi.repository import GtkSource
    HAS_GTKSOURCE = True
except (ValueError, ImportError):
    HAS_GTKSOURCE = False
from gi.repository import Gtk, Adw, Gio, GLib, GObject, Pango

import json
import os
import re
import html as html_mod
import zipfile
import threading
import requests
from pathlib import Path
from datetime import datetime

from .research import (
    ResearchError,
    build_claim_extraction_prompt,
    format_evidence,
    format_source_record,
    parse_claim_queries,
    search_europe_pmc,
)

# ---- Paths ----

DATA_DIR = Path.home() / ".local" / "share" / "cowriter"
WORK_DIR = DATA_DIR / "workspace"
VERSIONS_DIR = WORK_DIR / "versions"
AUTOSAVE_DIR = WORK_DIR / "autosaves"
NOTEBOOK_DIR = WORK_DIR / "notebook"
SOUL_FILE = DATA_DIR / "soul.md"
CONFIG_FILE = DATA_DIR / "config.json"

for d in [DATA_DIR, WORK_DIR, VERSIONS_DIR, AUTOSAVE_DIR, NOTEBOOK_DIR]:
    d.mkdir(parents=True, exist_ok=True)

PACKAGE_DIR = Path(__file__).resolve().parent

OLLAMA_URL = "http://localhost:11434/api/chat"

DEFAULT_SOUL = """# Co-Writer Soul
You are Co-Writer, a local LLM writing assistant.
Your job: help the user write, revise, expand, clarify, and organize text.
Preserve the user's voice. Never overwrite meaning unless directly asked.
When editing selected text, return only replacement text between:
<<<REPLACEMENT>>> and <<<END_REPLACEMENT>>>
When generating a full draft preview, return the complete revised document between:
<<<REVISED_DOCUMENT>>> and <<<END_REVISED_DOCUMENT>>>
Style: Thoughtful. Precise. Grounded. Not over-polished. Not corporate."""

CONTINUATION_SYSTEM = (
    "You are Co-Writer, a writing partner. Continue the supplied passage in the "
    "writer's voice. Return only 2 to 4 new sentences of prose. Do not repeat "
    "the passage or include labels, explanations, quotation marks, or markup."
)


def load_soul():
    return SOUL_FILE.read_text(encoding="utf-8", errors="replace") if SOUL_FILE.exists() else DEFAULT_SOUL


def init_soul():
    if not SOUL_FILE.exists():
        try:
            import importlib.resources
            with importlib.resources.files("cowriter").joinpath("soul.md").open("r", encoding="utf-8") as src:
                SOUL_FILE.write_text(src.read(), encoding="utf-8")
        except (FileNotFoundError, TypeError, ModuleNotFoundError):
            fallback = PACKAGE_DIR / "soul.md"
            SOUL_FILE.write_text(fallback.read_text(encoding="utf-8") if fallback.exists() else DEFAULT_SOUL, encoding="utf-8")

init_soul()


def load_config():
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_config(cfg):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def word_count(text):
    return len(re.findall(r'\b\w+\b', text))


def make_numbered_snapshot(text):
    numbered = "\n".join(f"{i+1}: {line}" for i, line in enumerate(text.splitlines()))
    return numbered


# ---- Ollama helpers ----

def get_available_models():
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=5)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
            return [m for m in models if "embed" not in m.lower()]
    except Exception:
        pass
    return []


def get_default_model():
    cfg = load_config()
    return cfg.get("model", "")

OLLAMA_MODEL = get_default_model()


# ============================================================
#  File import helpers
# ============================================================

def import_file_content(path):
    ext = Path(path).suffix.lower()
    if ext in (".txt", ".md"):
        return Path(path).read_text(encoding="utf-8", errors="replace")
    elif ext in (".html", ".htm"):
        c = Path(path).read_text(encoding="utf-8", errors="replace")
        c = re.sub(r'<script[^>]*>.*?</script>', '', c, flags=re.DOTALL)
        c = re.sub(r'<style[^>]*>.*?</style>', '', c, flags=re.DOTALL)
        c = re.sub(r'<[^>]+>', ' ', c)
        c = html_mod.unescape(c)
        c = re.sub(r'\s+', ' ', c)
        return c.strip()
    elif ext == ".pdf":
        from pypdf import PdfReader
        return '\n\n'.join(p.extract_text() or "" for p in PdfReader(path).pages)
    elif ext == ".docx":
        from docx import Document
        return '\n\n'.join(p.text for p in Document(path).paragraphs)
    elif ext == ".odt":
        from odf.opendocument import load
        doc = load(path)
        parts = []
        for el in doc.text.childNodes:
            if el.tagName == 'text:p':
                parts.append(''.join(ch.data for ch in el.childNodes if ch.nodeType == ch.TEXT_NODE))
        return '\n\n'.join(parts)
    elif ext == ".epub":
        with zipfile.ZipFile(path, 'r') as epub:
            parts = []
            for name in epub.namelist():
                if name.endswith(('.html', '.xhtml', '.htm')):
                    c = epub.read(name).decode('utf-8', errors='replace')
                    c = re.sub(r'<[^>]+>', ' ', c)
                    c = html_mod.unescape(c)
                    c = re.sub(r'\s+', ' ', c)
                    if c.strip():
                        parts.append(c.strip())
            return '\n\n'.join(parts)
    elif ext == ".mobi":
        import mobi, tempfile, shutil
        tdir, extracted = mobi.extract(path)
        try:
            parts = []
            for root, dirs, files in os.walk(extracted):
                for f in files:
                    if f.endswith(('.html', '.htm')):
                        c = Path(os.path.join(root, f)).read_text(encoding='utf-8', errors='replace')
                        c = re.sub(r'<[^>]+>', ' ', c)
                        c = html_mod.unescape(c)
                        c = re.sub(r'\s+', ' ', c)
                        if c.strip():
                            parts.append(c.strip())
            return '\n\n'.join(parts)
        finally:
            shutil.rmtree(tdir, ignore_errors=True)
    elif ext == ".rtf":
        from striprtf.striprtf import rtf_to_text
        return rtf_to_text(Path(path).read_text(encoding='utf-8', errors='replace'))
    return Path(path).read_text(encoding="utf-8", errors="replace")


# ============================================================
#  Main Application Window
# ============================================================

class CoWriterWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Co-Writer")
        self.set_default_size(1400, 900)
        # Breakpoints allow the content to shrink below its natural width.
        self.set_size_request(480, 360)

        self.chat_history = []
        self.open_tabs = {}  # page_widget → filepath
        self.tab_counter = 0
        self._available_models = []
        self._ai_action_buttons = []

        cfg = load_config()
        self.dark_mode = cfg.get("dark_mode", True)

        self._build_ui()
        self._refresh_file_tree()
        self._refresh_notebook()
        self._refresh_models()
        self._schedule_autosave()

    # ---- UI Construction ----

    def _build_ui(self):
        # Toolbar actions
        actions = Gio.SimpleActionGroup()
        for name, cb in [
            ("new-file", self._on_new), ("open-file", self._on_open),
            ("save", self._on_save), ("save-all", self._on_save_all),
            ("save-version", self._on_save_version), ("export", self._on_export),
            ("recover", self._on_recover), ("toggle-theme", self._on_toggle_theme),
        ]:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", cb)
            actions.add_action(action)
        self.insert_action_group("win", actions)

        # Header bar
        hb = Adw.HeaderBar()
        self._hb = hb

        self.files_toggle = Gtk.ToggleButton(icon_name="sidebar-show-symbolic")
        self.files_toggle.set_tooltip_text("Files and notebook")
        hb.pack_start(self.files_toggle)
        hb.pack_start(self._hb_btn("New document", "win.new-file", "document-new-symbolic"))
        hb.pack_start(self._hb_btn("Open document", "win.open-file", "document-open-symbolic"))
        hb.pack_start(self._hb_btn("Save document", "win.save", "document-save-symbolic"))

        menu = Gio.Menu()
        menu.append("Save All", "win.save-all")
        menu.append("Save Version", "win.save-version")
        menu.append("Export…", "win.export")
        menu.append("Recover Document…", "win.recover")
        menu.append("Toggle Dark / Light Theme", "win.toggle-theme")
        menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu)
        menu_button.set_tooltip_text("Document actions and appearance")
        hb.pack_end(menu_button)
        self.ai_toggle = Gtk.ToggleButton(label="AI")
        self.ai_toggle.set_tooltip_text("AI assistant")
        hb.pack_end(self.ai_toggle)

        # Toolbar view wraps content with headerbar
        toolbar_view = Adw.ToolbarView()
        toolbar_view.set_vexpand(True)
        toolbar_view.add_top_bar(hb)
        self.set_content(toolbar_view)

        # --- Main layout panel ---
        self.ai_split = Adw.OverlaySplitView(sidebar_position=Gtk.PackType.END)
        self.ai_split.set_min_sidebar_width(320)
        self.ai_split.set_max_sidebar_width(380)
        self.ai_split.set_sidebar_width_fraction(0.28)
        self.files_split = Adw.OverlaySplitView()
        self.files_split.set_min_sidebar_width(220)
        self.files_split.set_max_sidebar_width(280)
        self.files_split.set_sidebar_width_fraction(0.22)
        self.ai_split.set_content(self.files_split)
        toolbar_view.set_content(self.ai_split)

        # --- Left sidebar ---
        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar_scroll = Gtk.ScrolledWindow()
        sidebar_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sidebar_scroll.set_child(sidebar_box)
        sidebar_scroll.set_vexpand(True)
        self.files_split.set_sidebar(sidebar_scroll)

        # File tree header
        fb_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        fb_header.set_margin_start(6)
        fb_header.set_margin_end(6)
        fb_header.set_margin_top(6)
        fb_header.set_margin_bottom(3)
        fb_label = Gtk.Label(label="Files", halign=Gtk.Align.START)
        fb_label.add_css_class("heading")
        fb_header.append(fb_label)
        sidebar_box.append(fb_header)

        # File tree
        self.file_store = Gtk.TreeStore(str, str)  # display_name, filepath
        self.file_tree = Gtk.TreeView(model=self.file_store)
        self.file_tree.set_headers_visible(False)
        renderer = Gtk.CellRendererText()
        renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
        col = Gtk.TreeViewColumn("Name", renderer, text=0)
        col.set_expand(True)
        self.file_tree.insert_column(col, -1)
        self.file_tree.connect("row-activated", self._on_file_activated)

        fb_scroll = Gtk.ScrolledWindow()
        fb_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        fb_scroll.set_child(self.file_tree)
        fb_scroll.set_vexpand(True)
        sidebar_box.append(fb_scroll)

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sidebar_box.append(sep)

        # Notebook header
        nb_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        nb_header.set_margin_start(6)
        nb_header.set_margin_end(6)
        nb_header.set_margin_top(6)
        nb_header.set_margin_bottom(3)
        nb_label = Gtk.Label(label="Notebook", halign=Gtk.Align.START)
        nb_label.add_css_class("heading")
        nb_header.append(nb_label)
        nb_new_btn = Gtk.Button.new_with_label("+")
        nb_new_btn.set_has_frame(False)
        nb_new_btn.connect("clicked", self._on_new_note)
        nb_header.append(nb_new_btn)
        sidebar_box.append(nb_header)

        # Notebook search
        self.nb_search = Gtk.SearchEntry()
        self.nb_search.set_margin_start(6)
        self.nb_search.set_margin_end(6)
        self.nb_search.set_margin_bottom(3)
        self.nb_search.connect("search-changed", self._on_nb_search)
        sidebar_box.append(self.nb_search)

        # Notebook list
        self.nb_store = Gtk.StringList()
        self.nb_list = Gtk.ListView()
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._nb_factory_setup)
        factory.connect("bind", self._nb_factory_bind)
        self.nb_list.set_model(Gtk.SingleSelection(model=self.nb_store))
        self.nb_list.set_factory(factory)
        self.nb_list.connect("activate", self._on_note_activated)

        nb_scroll = Gtk.ScrolledWindow()
        nb_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        nb_scroll.set_child(self.nb_list)
        nb_scroll.set_vexpand(True)
        sidebar_box.append(nb_scroll)

        # --- Center: tabbed editor ---
        center_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        center_box.set_hexpand(True)
        center_box.set_vexpand(True)

        # Formatting toolbar
        fmt_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        fmt_bar.set_margin_start(6)
        fmt_bar.set_margin_top(6)
        fmt_bar.set_margin_bottom(3)

        for label, tag in [
            ("H1", "## "), ("H2", "### "), ("H3", "#### "),
            ("B", "**"), ("I", "*"), ("`", "`"),
            ("•", "- "), ("1.", "1. "), (">", "> "),
            ("[](", "[]()"), ("[[", "[[]]"),
        ]:
            b = self._fmt_btn(label, tag)
            fmt_bar.append(b)

        sep2 = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep2.set_margin_start(6)
        sep2.set_margin_end(6)
        fmt_bar.append(sep2)

        for label, cb in [("Preview", self._on_preview), ("AI Edit", self._on_ai_edit)]:
            b = Gtk.Button.new_with_label(label)
            b.set_has_frame(False)
            b.connect("clicked", cb)
            fmt_bar.append(b)

        # Keep formatting controls reachable without forcing a wide editor.
        fmt_scroll = Gtk.ScrolledWindow()
        fmt_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        fmt_scroll.set_propagate_natural_height(True)
        fmt_scroll.set_child(fmt_bar)
        center_box.append(fmt_scroll)

        # Editor notebook (tabs)
        self.edit_notebook = Gtk.Notebook()
        self.edit_notebook.set_scrollable(True)
        self.edit_notebook.set_hexpand(True)
        self.edit_notebook.set_vexpand(True)
        self.edit_notebook.connect("switch-page", self._on_tab_switched)
        center_box.append(self.edit_notebook)

        self.files_split.set_content(center_box)

        # --- Right: AI panel ---
        ai_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        ai_box.set_margin_start(6)
        ai_box.set_margin_end(6)
        ai_box.set_margin_top(6)

        ai_label = Gtk.Label(label="AI Assistant", halign=Gtk.Align.START)
        ai_label.add_css_class("heading")
        ai_box.append(ai_label)

        # Model selector
        model_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
        self.model_combo = Gtk.DropDown.new_from_strings(["Loading..."])
        self.model_combo.set_hexpand(True)
        self.model_combo.connect("notify::selected", self._on_model_changed)
        model_box.append(self.model_combo)
        refresh_btn = Gtk.Button.new_with_label("↻")
        refresh_btn.set_has_frame(False)
        refresh_btn.connect("clicked", lambda b: self._refresh_models())
        model_box.append(refresh_btn)
        ai_box.append(model_box)

        # Action buttons
        act_box = Gtk.FlowBox()
        act_box.set_selection_mode(Gtk.SelectionMode.NONE)
        act_box.set_homogeneous(True)
        act_box.set_min_children_per_line(1)
        act_box.set_max_children_per_line(3)
        act_box.set_column_spacing(2)
        act_box.set_row_spacing(2)
        for label, cb in [
            ("Ask", self._on_ask), ("Draft", self._on_draft),
            ("Continue", self._on_continue), ("Research", self._on_fact_check),
            ("Clear", self._on_clear_chat),
        ]:
            b = Gtk.Button.new_with_label(label)
            b.set_has_frame(False)
            b.connect("clicked", cb)
            act_box.insert(b, -1)
            if label != "Clear":
                self._ai_action_buttons.append(b)
        ai_box.append(act_box)

        # Chat output
        chat_scroll = Gtk.ScrolledWindow()
        chat_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.chat_view = Gtk.TextView()
        self.chat_view.set_editable(False)
        self.chat_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.chat_view.set_monospace(True)
        self.chat_buffer = self.chat_view.get_buffer()
        self.chat_buffer.create_tag("user", weight=Pango.Weight.BOLD)
        self.chat_buffer.create_tag("ai", style=Pango.Style.ITALIC)
        self.chat_buffer.create_tag("system", scale=0.9, style=Pango.Style.ITALIC)
        chat_scroll.set_child(self.chat_view)
        chat_scroll.set_vexpand(True)
        ai_box.append(chat_scroll)

        # Chat input
        input_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
        input_box.set_margin_bottom(6)
        self.chat_entry = Gtk.Entry()
        self.chat_entry.set_placeholder_text("Instruction...")
        self.chat_entry.set_hexpand(True)
        self.chat_entry.connect("activate", self._on_ask)
        input_box.append(self.chat_entry)
        ai_box.append(input_box)

        # Right panel scroll
        ai_scroll = Gtk.ScrolledWindow()
        ai_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        ai_scroll.set_child(ai_box)
        self.ai_split.set_sidebar(ai_scroll)
        self._setup_adaptive_layout()

        # Open initial document
        self._open_initial()

    def _setup_adaptive_layout(self):
        for split, button in [(self.files_split, self.files_toggle),
                              (self.ai_split, self.ai_toggle)]:
            split.bind_property("show-sidebar", button, "active",
                                GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE)
            split.connect("notify::show-sidebar", self._on_sidebar_shown)

        # Only the last matching window breakpoint applies, so the narrow
        # breakpoint includes both panes. Lengths in sp follow text scaling.
        medium = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 1180sp"))
        medium.add_setter(self.ai_split, "collapsed", True)
        self.add_breakpoint(medium)
        narrow = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 820sp"))
        narrow.add_setter(self.ai_split, "collapsed", True)
        narrow.add_setter(self.files_split, "collapsed", True)
        self.add_breakpoint(narrow)

    def _on_sidebar_shown(self, split, _pspec):
        # On small windows, open one drawer at a time.
        if split.get_collapsed() and split.get_show_sidebar():
            other = self.files_split if split is self.ai_split else self.ai_split
            if other.get_collapsed():
                other.set_show_sidebar(False)

    def _hb_btn(self, label, action, icon):
        b = Gtk.Button.new_from_icon_name(icon)
        b.set_tooltip_text(label)
        b.set_has_frame(False)
        b.set_action_name(action)
        return b

    def _fmt_btn(self, label, tag):
        b = Gtk.Button.new_with_label(label)
        b.set_has_frame(False)
        b.connect("clicked", lambda btn, t=tag: self._insert_format(t))
        b.set_tooltip_text(f"Insert {tag}")
        return b

    # ---- Sidebar Helpers ----

    def _refresh_file_tree(self):
        self.file_store.clear()
        ws = self.file_store.append(None, ["📁 workspace", str(WORK_DIR)])
        for label, path, exts in [
            ("📄 Drafts", WORK_DIR, [".md", ".txt"]),
            ("📚 Notebook", NOTEBOOK_DIR, [".md"]),
            ("📦 Versions", VERSIONS_DIR, [".md", ".txt"]),
        ]:
            if path.exists():
                node = self.file_store.append(ws, [label, str(path)])
                files = sorted([f for f in path.iterdir() if f.is_file() and f.suffix.lower() in exts],
                               key=lambda f: f.stat().st_mtime, reverse=True)
                for fp in files:
                    self.file_store.append(node, [fp.name, str(fp)])
        self.file_tree.expand_all()

    def _on_file_activated(self, tree, path, column):
        it = self.file_store.get_iter(path)
        filepath = self.file_store.get_value(it, 1)
        if Path(filepath).is_file():
            self._open_document(filepath)
            self._dismiss_files_drawer()

    def _dismiss_files_drawer(self):
        if self.files_split.get_collapsed():
            self.files_split.set_show_sidebar(False)

    # ---- Notebook Helpers ----

    def _nb_factory_setup(self, factory, list_item):
        label = Gtk.Label(halign=Gtk.Align.START, margin_start=6, margin_end=6, margin_top=2, margin_bottom=2)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        list_item.set_child(label)

    def _nb_factory_bind(self, factory, list_item):
        label = list_item.get_child()
        item = list_item.get_item()
        label.set_label(item.get_string())

    def _refresh_notebook(self):
        self.nb_store = Gtk.StringList()
        if NOTEBOOK_DIR.exists():
            for f in sorted(NOTEBOOK_DIR.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True):
                self.nb_store.append(f.stem.replace("_", " "))
        self.nb_list.set_model(Gtk.SingleSelection(model=self.nb_store))

    def _on_nb_search(self, entry):
        query = entry.get_text().lower()
        self.nb_store = Gtk.StringList()
        if not NOTEBOOK_DIR.exists():
            self.nb_list.set_model(Gtk.SingleSelection(model=self.nb_store))
            return
        for f in sorted(NOTEBOOK_DIR.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True):
            name = f.stem.replace("_", " ")
            if query in name.lower():
                self.nb_store.append(name)
            elif query:
                try:
                    if query in f.read_text(encoding="utf-8", errors="replace").lower():
                        self.nb_store.append(f"* {name}")
                except Exception:
                    pass
        self.nb_list.set_model(Gtk.SingleSelection(model=self.nb_store))

    def _on_note_activated(self, lv, idx):
        item = self.nb_store.get_string(idx).lstrip("* ")
        path = NOTEBOOK_DIR / f"{item.replace(' ', '_')}.md"
        if path.exists():
            self._open_document(str(path))
            self._dismiss_files_drawer()

    def _on_new_note(self, btn):
        name = f"note_{timestamp()}.md"
        path = NOTEBOOK_DIR / name
        path.write_text(f"# Note {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n", encoding="utf-8")
        self._open_document(str(path))
        self._refresh_notebook()
        self._dismiss_files_drawer()

    # ---- Editor Tab Management ----

    def _create_editor_page(self):
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        if HAS_GTKSOURCE:
            buf = GtkSource.Buffer()
            lm = GtkSource.LanguageManager()
            buf.set_language(lm.get_language("markdown"))
            buf.set_highlight_syntax(True)
            buf.set_style_scheme(GtkSource.StyleSchemeManager.get_default().get_scheme(
                "Adwaita-dark" if self.dark_mode else "Adwaita"))
            view = GtkSource.View(buffer=buf)
            view.set_show_line_numbers(True)
        else:
            buf = Gtk.TextBuffer()
            view = Gtk.TextView(buffer=buf)

        view.set_wrap_mode(Gtk.WrapMode.WORD)
        view.set_monospace(True)
        view.set_left_margin(8)
        view.set_right_margin(8)
        view.set_top_margin(8)
        view.set_bottom_margin(8)

        scroll.set_child(view)

        label_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
        self.tab_counter += 1
        lbl = Gtk.Label(label="Untitled")
        close_btn = Gtk.Button.new_from_icon_name("window-close-symbolic")
        close_btn.set_has_frame(False)
        close_btn.connect("clicked", lambda b: self._close_tab_by_page(scroll))
        label_box.append(lbl)
        label_box.append(close_btn)

        return scroll, view, buf, label_box

    def _open_document(self, path):
        path = Path(path).resolve()

        # Check if already open
        for i in range(self.edit_notebook.get_n_pages()):
            page = self.edit_notebook.get_nth_page(i)
            if str(path) == self.open_tabs.get(page, ""):
                self.edit_notebook.set_current_page(i)
                return

        scroll, view, buf, tab_label = self._create_editor_page()
        filepath = str(path)

        try:
            content = import_file_content(filepath)
        except Exception as e:
            content = f"# Error opening file\n\n{e}\n\nTry using Recover if the file is corrupt."
        buf.set_text(content, -1)

        tab_label.get_first_child().set_label(path.name)
        self.edit_notebook.append_page(scroll, tab_label)
        self.edit_notebook.set_current_page(self.edit_notebook.get_n_pages() - 1)
        self.open_tabs[scroll] = filepath

        self._refresh_file_tree()

    def _get_current_page(self):
        n = self.edit_notebook.get_current_page()
        if n >= 0:
            page = self.edit_notebook.get_nth_page(n)
            return page, self._get_view_from_page(page), self._get_buf_from_page(page)
        return None, None, None

    def _get_view_from_page(self, page):
        return page.get_child()

    def _get_buf_from_page(self, page):
        return self._get_view_from_page(page).get_buffer()

    def _close_tab_by_page(self, page):
        for i in range(self.edit_notebook.get_n_pages()):
            if self.edit_notebook.get_nth_page(i) is page:
                self.edit_notebook.remove_page(i)
                if page in self.open_tabs:
                    del self.open_tabs[page]
                break

    def _on_tab_switched(self, nb, page, idx):
        pass

    def _open_initial(self):
        draft = WORK_DIR / "current_draft.md"
        if draft.exists():
            self._open_document(str(draft))
        else:
            # Create a welcome document
            welcome = "# Co-Writer\n\nWelcome! Start writing here, or open a file from the sidebar.\n\n- **+ New** — create a new file\n- **Open** — import any document\n- **Recover** — use Documancy to recover corrupt files with AI\n- **Export** — save as PDF, DOCX, ODT, and more\n"
            draft.write_text(welcome, encoding="utf-8")
            self._open_document(str(draft))

    # ---- Formatting Toolbar ----

    def _insert_format(self, tag):
        _, view, buf = self._get_current_page()
        if not buf:
            return

        if buf.get_has_selection():
            start = buf.get_selection_bound()
            end = buf.get_iter_at_mark(buf.get_insert())
            if start.compare(end) > 0:
                start, end = end, start
            sel_text = buf.get_text(start, end, False)
            buf.delete(start, end)

            if tag in ("**", "*", "`"):
                buf.insert(start, f"{tag}{sel_text}{tag}", -1)
            elif tag in ("## ", "### ", "#### ", "- ", "1. ", "> "):
                buf.insert(start, f"{tag}{sel_text}", -1)
            elif tag == "[[]]":
                buf.insert(start, f"[[{sel_text}]]", -1)
            elif tag == "[]()":
                buf.insert(start, f"[{sel_text}]()", -1)
        else:
            cursor = buf.get_iter_at_mark(buf.get_insert())
            buf.insert(cursor, tag, -1)
            if tag in ("**", "*", "`"):
                end_mark = buf.get_iter_at_mark(buf.get_insert())
                buf.place_cursor(end_mark)

    # ---- AI Chat ----

    def _append_chat(self, speaker, text):
        end = self.chat_buffer.get_end_iter()
        tag_name = {"You": "user", "System": "system"}.get(speaker, "ai")
        self.chat_buffer.insert_with_tags_by_name(end, f"\n{speaker}: {text}\n", tag_name)
        # Scroll to bottom
        adj = self.chat_view.get_parent().get_vadjustment()
        GLib.idle_add(lambda: adj.set_value(adj.get_upper()))

    def _stream_chat(self, chunk):
        end = self.chat_buffer.get_end_iter()
        self.chat_buffer.insert(end, chunk, -1)
        adj = self.chat_view.get_parent().get_vadjustment()
        GLib.idle_add(lambda: adj.set_value(adj.get_upper()))

    def _on_clear_chat(self, btn):
        self.chat_buffer.set_text("", -1)
        self.chat_history = []

    def _call_ollama(
        self,
        prompt,
        callback=None,
        error_callback=None,
        show_stream=True,
        include_history=True,
        record_history=True,
        temperature=0.7,
        system_prompt=None,
        think=None,
    ):
        if not OLLAMA_MODEL or OLLAMA_MODEL not in self._available_models:
            self._append_chat("System", "Start Ollama and choose an installed model first.")
            if error_callback:
                error_callback()
            return False

        messages = [{"role": "system", "content": load_soul() if system_prompt is None else system_prompt}]
        if include_history:
            messages.extend(self.chat_history[-8:])
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": OLLAMA_MODEL,
            "messages": messages,
            "stream": True,
            "options": {"temperature": temperature},
        }
        if think is not None:
            payload["think"] = think
        response_text = ""

        def run():
            nonlocal response_text
            try:
                with requests.post(OLLAMA_URL, json=payload, stream=True, timeout=180) as r:
                    r.raise_for_status()
                    for line in r.iter_lines():
                        if not line:
                            continue
                        data = json.loads(line.decode("utf-8"))
                        if "message" in data and "content" in data["message"]:
                            chunk = data["message"]["content"]
                            response_text += chunk
                            if show_stream:
                                GLib.idle_add(self._stream_chat, chunk)
                        if data.get("done"):
                            break
            except Exception as e:
                GLib.idle_add(self._append_chat, "System", f"Ollama error: {e}")
                if error_callback:
                    GLib.idle_add(error_callback)
                return

            if record_history:
                self.chat_history.append({"role": "user", "content": prompt})
                self.chat_history.append({"role": "assistant", "content": response_text})

            if callback:
                GLib.idle_add(callback, response_text)

        threading.Thread(target=run, daemon=True).start()
        return True

    def _on_ask(self, *args):
        text = self.chat_entry.get_text().strip()
        if not text:
            return
        self.chat_entry.set_text("")

        _, _, buf = self._get_current_page()
        doc = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False) if buf else ""
        numbered = make_numbered_snapshot(doc)

        prompt = f"Current numbered snapshot:\n\n{numbered}\n\nUser message:\n{text}"
        self._append_chat("You", text)
        self._append_chat("AI", "")
        self._call_ollama(prompt)

    def _on_draft(self, btn):
        text = self.chat_entry.get_text().strip() or "Create a revised full draft."
        self.chat_entry.set_text("")
        _, _, buf = self._get_current_page()
        doc = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False) if buf else ""
        numbered = make_numbered_snapshot(doc)
        recent = "\n\n".join(f"{m['role'].upper()}: {m['content']}" for m in self.chat_history[-8:])

        prompt = f"{numbered}\n\nRecent chat:\n{recent}\n\nUser: {text}\nReturn complete revised document between <<<REVISED_DOCUMENT>>> and <<<END_REVISED_DOCUMENT>>>."

        self._append_chat("You", f"Draft: {text}")
        self._append_chat("AI", "")

        def handle_draft(resp):
            if "<<<REVISED_DOCUMENT>>>" in resp and "<<<END_REVISED_DOCUMENT>>>" in resp:
                s = resp.index("<<<REVISED_DOCUMENT>>>") + len("<<<REVISED_DOCUMENT>>>")
                e = resp.index("<<<END_REVISED_DOCUMENT>>>")
                revised = resp[s:e].strip()
                path = VERSIONS_DIR / f"draft_{timestamp()}.md"
                path.write_text(revised, encoding="utf-8")
                self._open_document(str(path))
                self._append_chat("System", f"Draft saved: {path.name}")

        self._call_ollama(prompt, handle_draft)

    def _on_continue(self, btn):
        _, _, buf = self._get_current_page()
        if not buf:
            return
        selected = buf.get_has_selection()
        if selected:
            start = buf.get_iter_at_mark(buf.get_insert())
            end = buf.get_iter_at_mark(buf.get_selection_bound())
            if start.compare(end) > 0:
                start, end = end, start
            passage = buf.get_text(start, end, False)
            insert_at = end
            prompt = f"Selected passage to continue:\n\n{passage}\n\n"
        else:
            insert_at = buf.get_iter_at_mark(buf.get_insert())
            before_cursor = buf.get_text(buf.get_start_iter(), insert_at, False)
            tail = "\n".join(before_cursor.splitlines()[-25:])
            prompt = f"Continue writing from here:\n\n{tail}\n\n"
        insert_mark = buf.create_mark(None, insert_at, True)
        prompt += (
            "Write only a 2-4 sentence continuation immediately after this passage. "
            "Preserve the user's voice. Do not add an introduction, commentary, or quotation marks."
        )
        self._append_chat("You", "Continue writing...")
        self._append_chat("AI", "")

        def handle_continuation(response, retry=False):
            continuation = response.strip()
            if not continuation and not retry:
                self._append_chat("System", "No continuation text received; retrying once.")
                request_continuation(retry=True)
                return
            self._show_continuation_preview(buf, insert_mark, continuation, selected)

        def request_continuation(retry=False):
            self._call_ollama(
                prompt,
                lambda response: handle_continuation(response, retry),
                lambda: self._delete_marks(buf, insert_mark),
                include_history=False,
                record_history=False,
                temperature=0.4 if retry else 0.7,
                system_prompt=CONTINUATION_SYSTEM,
                think=False,
            )

        request_continuation()

    def _show_continuation_preview(self, buf, insert_mark, continuation, selected):
        if not continuation:
            buf.delete_mark(insert_mark)
            self._append_chat("System", "The model returned an empty continuation.")
            return

        dialog = Adw.MessageDialog.new(self, "Insert continuation?", continuation)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("insert", "Insert")
        dialog.set_response_appearance("insert", Adw.ResponseAppearance.SUGGESTED)
        dialog.connect(
            "response",
            lambda d, response: self._handle_continuation_response(
                response, buf, insert_mark, continuation, selected
            ),
        )
        dialog.present()

    def _handle_continuation_response(self, response, buf, insert_mark, continuation, selected):
        if response == "insert" and not insert_mark.get_deleted():
            cursor = buf.get_iter_at_mark(insert_mark)
            if cursor.starts_line():
                prefix = ""
            elif selected and cursor.ends_line():
                prefix = "\n"
            else:
                prefix = " "
            buf.insert(cursor, prefix + continuation, -1)
            self._append_chat("System", "Continuation inserted into the draft.")
        if not insert_mark.get_deleted():
            buf.delete_mark(insert_mark)

    def _on_fact_check(self, button):
        _, _, buf = self._get_current_page()
        if not buf:
            return

        if buf.get_has_selection():
            start = buf.get_iter_at_mark(buf.get_insert())
            end = buf.get_iter_at_mark(buf.get_selection_bound())
            if start.compare(end) > 0:
                start, end = end, start
            passage = buf.get_text(start, end, False)
            scope = "the selected passage"
        else:
            cursor = buf.get_iter_at_mark(buf.get_insert())
            passage = buf.get_text(buf.get_start_iter(), cursor, False)[-6000:]
            scope = "the text before the cursor"

        passage = passage.strip()
        if not passage:
            self._append_chat("System", "Write or select a passage to fact-check first.")
            return

        button.set_sensitive(False)
        self._append_chat("You", f"Run an evidence audit on {scope}.")
        self._append_chat(
            "System",
            "Finding checkable claims locally. Only short search queries will be sent to Europe PMC.",
        )

        extraction_prompt = build_claim_extraction_prompt(passage)

        def handle_claims(response):
            try:
                claims = parse_claim_queries(response)
            except ResearchError as exc:
                self._append_chat("System", str(exc))
                button.set_sensitive(True)
                return

            self._append_chat("System", f"Searching scholarly literature for {len(claims)} claim(s)...")

            def gather_evidence():
                try:
                    claim_sources = [
                        (
                            claim,
                            search_europe_pmc(claim.query)
                            if claim.kind in {"research_claim", "clinical_interpretation"}
                            else [],
                        )
                        for claim in claims
                    ]
                except ResearchError as exc:
                    GLib.idle_add(self._fact_check_failed, button, str(exc))
                    return
                GLib.idle_add(self._finish_fact_check, button, claim_sources)

            threading.Thread(target=gather_evidence, daemon=True).start()

        self._call_ollama(
            extraction_prompt,
            handle_claims,
            lambda: button.set_sensitive(True),
            show_stream=False,
            include_history=False,
            record_history=False,
            temperature=0.0,
        )

    def _fact_check_failed(self, button, message):
        self._append_chat("System", message)
        button.set_sensitive(True)

    def _finish_fact_check(self, button, claim_sources):
        evidence = format_evidence(claim_sources)
        prompt = f"""Act as a careful evidence auditor. Evaluate each statement using only the classification and scholarly metadata or abstracts below.

For each numbered statement, provide these fields:
- Classification: lived experience, research claim, clinical interpretation, or legal claim
- Finding: Supported, Mixed, Contradicted, Not verified, Personal account, or Professional review needed
- Confidence: High, Moderate, Low, or Insufficient, with one sentence explaining why
- Evidence: a concise explanation distinguishing correlation from causation
- Population: ages, setting, sample, and applicability when the abstracts provide them; otherwise say unknown
- Safer wording: preserve first-person accounts exactly, but suggest appropriately qualified wording for research claims
- Sources: supplied bracket numbers and URLs

Never dispute or rewrite a lived-experience statement merely because it lacks a citation. Never diagnose a child, parent, or other individual. Flag clinical interpretations for qualified professional review and legal claims for current jurisdiction-specific review. Never invent a citation or imply that an abstract proves more than it reports. Citation counts are context, not quality scores. If evidence is indirect, old, conflicting, or absent, say so. End with a limitations section. This is a research aid, not medical or legal advice.

EVIDENCE:
{evidence}"""

        self._append_chat("AI", "")
        self._call_ollama(
            prompt,
            lambda response: self._save_evidence_audit(button, response, claim_sources),
            lambda: button.set_sensitive(True),
            include_history=False,
            record_history=False,
            temperature=0.2,
        )

    def _save_evidence_audit(self, button, response, claim_sources):
        report = (
            "# Co-Writer Evidence Audit\n\n"
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            "> This report is a research aid, not medical or legal advice. "
            "Open and assess the cited sources before relying on a finding.\n\n"
            "## Assessment\n\n"
            f"{response.strip()}\n\n"
            "## Claim-to-source record\n\n"
            f"{format_source_record(claim_sources)}\n"
        )
        path = VERSIONS_DIR / f"evidence_audit_{timestamp()}.md"
        try:
            path.write_text(report, encoding="utf-8")
            self._open_document(str(path))
            self._append_chat("System", f"Evidence audit saved: {path.name}")
        except OSError as exc:
            self._append_chat("System", f"Could not save evidence audit: {exc}")
        finally:
            button.set_sensitive(True)

    def _on_ai_edit(self, btn):
        self.ai_split.set_show_sidebar(True)
        _, view, buf = self._get_current_page()
        if not buf or not buf.get_has_selection():
            self._append_chat("System", "Select text in the editor first.")
            return

        start = buf.get_iter_at_mark(buf.get_insert())
        end = buf.get_iter_at_mark(buf.get_selection_bound())
        if start.compare(end) > 0:
            start, end = end, start
        sel_text = buf.get_text(start, end, False)
        start_mark = buf.create_mark(None, start, True)
        end_mark = buf.create_mark(None, end, False)

        instruction = self.chat_entry.get_text().strip() or "Improve this text."
        self.chat_entry.set_text("")

        doc = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
        numbered = make_numbered_snapshot(doc)
        prompt = f"{numbered}\n\nSelected text:\n{sel_text}\n\nInstruction: {instruction}\n\nReturn replacement between <<<REPLACEMENT>>> and <<<END_REPLACEMENT>>>."

        self._append_chat("You", f"Edit: {instruction}")
        self._append_chat("AI", "")

        def handle_edit(resp):
            if "<<<REPLACEMENT>>>" in resp and "<<<END_REPLACEMENT>>>" in resp:
                s = resp.index("<<<REPLACEMENT>>>") + len("<<<REPLACEMENT>>>")
                e = resp.index("<<<END_REPLACEMENT>>>")
                replacement = resp[s:e].strip()
                self._show_edit_preview(buf, start_mark, end_mark, replacement, sel_text)
            else:
                buf.delete_mark(start_mark)
                buf.delete_mark(end_mark)
                self._append_chat("System", "The model did not return a usable replacement block.")

        self._call_ollama(
            prompt,
            handle_edit,
            lambda: self._delete_marks(buf, start_mark, end_mark),
        )

    @staticmethod
    def _delete_marks(buf, *marks):
        for mark in marks:
            if not mark.get_deleted():
                buf.delete_mark(mark)

    def _show_edit_preview(self, buf, start_mark, end_mark, replacement, original):
        start = buf.get_iter_at_mark(start_mark)
        end = buf.get_iter_at_mark(end_mark)
        if buf.get_text(start, end, False) != original:
            buf.delete_mark(start_mark)
            buf.delete_mark(end_mark)
            self._append_chat("System", "The selected text changed while the model was responding; the edit was not applied.")
            return

        dialog = Adw.MessageDialog.new(self, "Accept AI Edit?", replacement)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("accept", "Accept")
        dialog.set_response_appearance("accept", Adw.ResponseAppearance.SUGGESTED)
        dialog.connect(
            "response",
            lambda d, resp: self._handle_edit_response(
                resp, buf, start_mark, end_mark, replacement, original
            ),
        )
        dialog.present()

    def _handle_edit_response(self, resp, buf, start_mark, end_mark, replacement, original):
        if resp == "accept" and not start_mark.get_deleted() and not end_mark.get_deleted():
            start = buf.get_iter_at_mark(start_mark)
            end = buf.get_iter_at_mark(end_mark)
            if buf.get_text(start, end, False) != original:
                self._append_chat("System", "The selected text changed before acceptance; the edit was not applied.")
                buf.delete_mark(start_mark)
                buf.delete_mark(end_mark)
                return

            before_path = VERSIONS_DIR / f"before_edit_{timestamp()}.md"
            before_path.write_text(buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False), encoding="utf-8")

            buf.delete(start, end)
            buf.insert(start, replacement, -1)

            after_path = VERSIONS_DIR / f"after_edit_{timestamp()}.md"
            after_path.write_text(buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False), encoding="utf-8")
            self._append_chat("System", "Edit accepted. Before/after saved.")
        if not start_mark.get_deleted():
            buf.delete_mark(start_mark)
        if not end_mark.get_deleted():
            buf.delete_mark(end_mark)

    def _on_preview(self, btn):
        _, _, buf = self._get_current_page()
        if not buf:
            return
        doc = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)

        dialog = Adw.MessageDialog.new(self, "Preview", doc[:500] + ("..." if len(doc) > 500 else ""))
        dialog.add_response("close", "Close")
        dialog.present()

    # ---- Model ----

    def _refresh_models(self):
        models = get_available_models()
        self._available_models = models
        display_models = models or ["(Ollama not running)"]

        # Rebuild string list
        sl = Gtk.StringList()
        for m in display_models:
            sl.append(m)
        self.model_combo.set_model(sl)

        global OLLAMA_MODEL
        if OLLAMA_MODEL in models:
            self.model_combo.set_selected(models.index(OLLAMA_MODEL))
        elif models:
            OLLAMA_MODEL = models[0]
            self.model_combo.set_selected(0)
        else:
            OLLAMA_MODEL = ""
            self.model_combo.set_selected(0)

        for button in self._ai_action_buttons:
            button.set_sensitive(bool(models))

    def _on_model_changed(self, combo, pspec):
        global OLLAMA_MODEL
        sel = combo.get_selected_item()
        if sel and isinstance(sel, Gtk.StringObject) and sel.get_string() in self._available_models:
            OLLAMA_MODEL = sel.get_string()
            cfg = load_config()
            cfg["model"] = OLLAMA_MODEL
            save_config(cfg)

    # ---- File Actions ----

    def _on_new(self, action, param):
        dialog = Gtk.FileDialog.new()
        dialog.set_title("Create New File")
        dialog.set_initial_folder(Gio.File.new_for_path(str(WORK_DIR)))
        dialog.set_initial_name("untitled.md")

        def save_cb(dlg, result):
            try:
                gf = dlg.save_finish(result)
                path = gf.get_path()
                Path(path).write_text("# Untitled\n\n", encoding="utf-8")
                self._open_document(path)
            except GLib.Error:
                pass
        dialog.save(self, None, save_cb)

    def _on_open(self, action, param):
        dialog = Gtk.FileDialog.new()
        dialog.set_title("Open Document")

        filter_all = Gtk.FileFilter()
        filter_all.set_name("All supported")
        for ext in ["*.txt", "*.md", "*.html", "*.htm", "*.pdf", "*.docx", "*.odt", "*.epub", "*.mobi", "*.rtf"]:
            filter_all.add_pattern(ext)
        dialog.set_default_filter(filter_all)

        def open_cb(dlg, result):
            try:
                gf = dlg.open_finish(result)
                self._open_document(gf.get_path())
            except GLib.Error:
                pass
        dialog.open(self, None, open_cb)

    def _on_save(self, action, param):
        page, _, buf = self._get_current_page()
        if page and buf and page in self.open_tabs:
            path = self.open_tabs[page]
            content = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
            Path(path).write_text(content, encoding="utf-8")
            self._append_chat("System", f"Saved: {Path(path).name}")

    def _on_save_all(self, action, param):
        for page, path in list(self.open_tabs.items()):
            buf = self._get_buf_from_page(page)
            if buf:
                content = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
                Path(path).write_text(content, encoding="utf-8")
        self._append_chat("System", "All files saved.")

    def _on_save_version(self, action, param):
        _, _, buf = self._get_current_page()
        if not buf:
            return
        path = VERSIONS_DIR / f"version_{timestamp()}.md"
        path.write_text(buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False), encoding="utf-8")
        self._append_chat("System", f"Version saved: {path.name}")
        self._refresh_file_tree()

    def _on_export(self, action, param):
        _, _, buf = self._get_current_page()
        if not buf:
            return
        content = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)

        dialog = Gtk.FileDialog.new()
        dialog.set_title("Export Document")
        dialog.set_initial_name("document.md")

        def save_cb(dlg, result):
            try:
                gf = dlg.save_finish(result)
                path = gf.get_path()
                ext = Path(path).suffix.lower()
                if ext in (".txt", ".md"):
                    Path(path).write_text(content, encoding="utf-8")
                elif ext == ".html":
                    h = f"<!DOCTYPE html>\n<html><head><meta charset=\"UTF-8\"><title>Doc</title>\n<style>body{{font-family:Georgia;max-width:800px;margin:40px auto;padding:20px;line-height:1.6}}pre{{font-family:monospace;white-space:pre-wrap}}</style></head>\n<body><pre>{html_mod.escape(content)}</pre></body></html>"
                    Path(path).write_text(h, encoding="utf-8")
                elif ext == ".pdf":
                    from reportlab.lib.pagesizes import letter
                    from reportlab.pdfgen import canvas
                    c = canvas.Canvas(path, pagesize=letter)
                    w, h = letter
                    c.setFont("Courier", 10)
                    t = c.beginText(72, h - 72)
                    t.setFont("Courier", 10)
                    for line in content.split('\n'):
                        t.textLine(line)
                    c.drawText(t)
                    c.save()
                elif ext == ".docx":
                    from docx import Document
                    from docx.shared import Pt
                    doc = Document()
                    doc.styles['Normal'].font.name = 'Courier New'
                    doc.styles['Normal'].font.size = Pt(10)
                    for line in content.split('\n'):
                        doc.add_paragraph(line)
                    doc.save(path)
                elif ext == ".odt":
                    from odf.opendocument import OpenDocumentText
                    from odf.style import Style, TextProperties
                    from odf.text import P
                    odoc = OpenDocumentText()
                    sty = Style(name="Mono", family="paragraph")
                    sty.addElement(TextProperties(fontname="Courier New", fontsize="10pt"))
                    odoc.automaticstyles.addElement(sty)
                    for line in content.split('\n'):
                        odoc.text.addElement(P(text=line, stylename=sty))
                    odoc.save(path)
                self._append_chat("System", f"Exported: {Path(path).name}")
            except GLib.Error:
                pass
            except ImportError as e:
                self._append_chat("System", str(e))
        dialog.save(self, None, save_cb)

    def _on_recover(self, action, param):
        dialog = Gtk.FileDialog.new()
        dialog.set_title("Select corrupt file to recover")

        def open_cb(dlg, result):
            try:
                gf = dlg.open_finish(result)
                path = gf.get_path()
                self._do_recover(path)
            except GLib.Error:
                pass
        dialog.open(self, None, open_cb)

    def _do_recover(self, path):
        # Try normal import first
        try:
            content = import_file_content(path)
            if content and len(content.strip()) > 10:
                self._open_document(path)
                self._append_chat("System", f"File opened normally: {Path(path).name}")
                return
        except Exception:
            pass

        try:
            with open(path, 'rb') as f:
                raw = f.read()
        except Exception as e:
            self._append_chat("System", f"Cannot read: {e}")
            return

        size_kb = len(raw) / 1024
        try:
            text = raw.decode('utf-8', errors='replace')
        except Exception:
            text = raw.hex()

        if len(text) > 24000:
            text = text[:12000] + "\n[...TRUNCATED...]\n" + text[-12000:]

        ext = Path(path).suffix.lower()
        fname = Path(path).name

        prompt = f"""DOCUMENT RECOVERY
Filename: {fname} | Type: {ext} | Size: {size_kb:.1f}KB
This is a corrupt/unreadable document. Reconstruct readable text from the raw content below. Ignore binary garbage. Return as clean markdown.

Raw content:
---
{text}
---"""

        self._append_chat("System", f"Recovering: {fname} ({size_kb:.1f}KB)")
        self._append_chat("AI", "Analyzing corrupt file...")

        def handle_recovery(resp):
            rpath = VERSIONS_DIR / f"recovered_{Path(fname).stem}_{timestamp()}.md"
            rpath.write_text(resp, encoding="utf-8")
            self._open_document(str(rpath))
            self._append_chat("System", f"Recovery complete: {rpath.name}")

        self._call_ollama(prompt, handle_recovery)

    def _on_toggle_theme(self, action, param):
        mgr = Adw.StyleManager.get_default()
        current = mgr.get_dark()
        mgr.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT if current else Adw.ColorScheme.FORCE_DARK)
        self.dark_mode = not current
        cfg = load_config()
        cfg["dark_mode"] = self.dark_mode
        save_config(cfg)

        # Re-apply source view style schemes if available
        if HAS_GTKSOURCE:
            for i in range(self.edit_notebook.get_n_pages()):
                page = self.edit_notebook.get_nth_page(i)
                buf = self._get_buf_from_page(page)
                if buf and isinstance(buf, GtkSource.Buffer):
                    buf.set_style_scheme(GtkSource.StyleSchemeManager.get_default().get_scheme(
                        "Adwaita-dark" if self.dark_mode else "Adwaita"))

    # ---- Autosave ----

    def _schedule_autosave(self):
        for page, path in list(self.open_tabs.items()):
            try:
                buf = self._get_buf_from_page(page)
                if buf:
                    content = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
                    ap = AUTOSAVE_DIR / f"{Path(path).stem}.autosave.md"
                    ap.write_text(content, encoding="utf-8")
            except Exception:
                pass
        GLib.timeout_add_seconds(5, self._schedule_autosave)


# ============================================================
#  Application Entry Point
# ============================================================

class CoWriterApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="com.github.chukrobertson.cowriter",
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = CoWriterWindow(self)
        win.present()


def main():
    app = CoWriterApp()
    return app.run(None)


if __name__ == "__main__":
    main()
