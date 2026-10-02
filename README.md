# Co-Writer v4

Local research and writing companion for the desktop, with **Documancy** for opening, editing, reformatting, and recovering documents. Built for Ubuntu/GNOME with local AI via [Ollama](https://ollama.com).

<p align="center">
  <strong>Open · Edit · Recover · Export · AI</strong>
</p>

---

## Features

### 📂 Documancy
- **Multi-tab editor** — open and work on multiple documents simultaneously
- **9 import formats** — TXT, MD, HTML, PDF, DOCX, ODT, EPUB, MOBI, RTF
- **6 export formats** — TXT, MD, HTML, PDF, DOCX, ODT
- **File browser sidebar** — workspace tree with drafts, versions, and notebook sections
- **Adaptive panes** — AI hides first below 1180 logical pixels; Files/Notebook hides below 820. Header buttons reopen them as drawers, and widening the window restores them.
- **Markdown formatting toolbar** — headings, bold, italic, lists, links, code, blockquotes
- **Full Markdown preview** — readable headings, lists, emphasis, code, tables, and clickable links for the entire document; remote images are not fetched
- **Find and replace** — case-sensitive or insensitive search, next/previous matches, and Replace All as a single undo operation

### 🤖 AI Assistant (Ollama)
- **Model auto-detection** — automatically finds your installed Ollama models
- **Configurable model selector** — switch models from the UI, persisted across sessions
- **Guided task selector** — model controls at the top, conversation in the middle, and explained tasks with input at the bottom
- **Chat interface** — ask questions, get feedback, request rewrites
- **Edit selection** — select text, give an instruction, accept or reject the AI edit
- **Generate draft** — produce a full revised document from chat context
- **Help me write** — preview a 2-4 sentence continuation after selected text, or at the cursor when nothing is selected
- **Check claims & sources** — assess highlighted claims using Europe PMC, arXiv and OpenAlex, with linked evidence reports
- **Activity and Stop** — see connection, writing, and research stages; stop an operation without applying a late response
- **Responsive model discovery** — Ollama model lookup runs in the background while you edit

### 🏥 Document Recovery (NEW)
- **LLM-powered recovery** — feed corrupt or unreadable files to the AI for reconstruction
- Reads raw bytes from damaged PDFs, DOCX, EPUB, and other formats
- LLM extracts readable text, reconstructs structure, and notes gaps
- Recovery results saved as clean markdown

### 📓 Zettelkasten Notebook
- **Quick notes** — create linked notes in the workspace notebook
- **Notebook-ready Markdown** — use `[[wikilinks]]` while organizing related notes
- **Search** — filter notes by title or content

### 💾 Data Management
- **Autosave** — every 5 seconds, per-tab, to autosave directory
- **Save feedback** — changed tabs show a dot, with Saved, Unsaved changes, or Autosaved status and word counts
- **Close protection** — Save, Discard, or Cancel before closing changed tabs or quitting
- **Draft recovery** — restore an unsaved recovery copy after reopening, without overwriting its original file
- **Workspace memory** — restore window size, maximized state, tabs, cursor positions, and pane preferences
- **Version snapshots** — save timestamped versions of any document
- **Dark/light theme** — toggle persisted in config
- **Config persistence** — model choice, theme and source collection choices saved to `~/.local/share/cowriter/config.json`

---

## Installation

### Quick Install (Recommended)

```bash
git clone https://github.com/chukrobertson/co-writer.git
cd co-writer
./install.sh
```

Installs to `~/.local/` — no sudo needed. Launch "Co-Writer" from your GNOME applications menu.

### Manual

```bash
pip install -e .
cowriter-gui
```

### Uninstall

```bash
./uninstall.sh
```

---

## Requirements

| Requirement | Package | Notes |
|---|---|---|
| Python 3.7+ | `python3` | |
| GTK 4.10+ + libadwaita 1.4+ | `gir1.2-gtk-4.0`, `gir1.2-adw-1` | Required for file dialogs and adaptive panes |
| PyGObject | `python3-gi` | Python bindings for GTK and libadwaita |
| GtkSourceView 5 | `gir1.2-gtksource-5` | Optional syntax highlighting and line numbers |
| Requests | `python3-requests` | Required for Ollama |
| Markdown parser | `python3-markdown-it` / `markdown-it-py` | Required for the native Markdown preview; pip installs it with the app |
| **Ollama** | [ollama.com](https://ollama.com) | For AI features (optional, UI works without) |
| Internet connection | — | Only required for scholarly fact-check searches |

### Optional Import/Export Libraries

| Library | Format | apt package | pip package |
|---|---|---|---|
| reportlab | PDF export | `python3-reportlab` | `reportlab` |
| pypdf | PDF import | `python3-pypdf` | `pypdf` |
| python-docx | DOCX import/export | `python3-docx` | `python-docx` |
| odfpy | ODT import/export | `python3-odf` | `odfpy` |
| striprtf | RTF import | `python3-striprtf` | `striprtf` |
| mobi | MOBI import | — (pip only) | `mobi` |

All libraries are **permissively licensed** (MIT/BSD/Apache 2.0) — no GPL concerns.

---

## File Locations

```
~/.local/
├── bin/cowriter-gui            # Entry point
└── share/
    ├── applications/
    │   └── com.github.chukrobertson.cowriter.desktop    # GNOME app menu
    ├── icons/hicolor/scalable/apps/
    │   └── com.github.chukrobertson.cowriter.svg        # App icon
    ├── metainfo/
    │   └── com.github.chukrobertson.cowriter.metainfo.xml
    └── cowriter/              # User data
        ├── config.json
        ├── session.json      # Local window, tabs, cursors, and pane preferences
        ├── soul.md
        └── workspace/
            ├── current_draft.md
            ├── autosaves/
            ├── versions/
            └── notebook/     # Zettelkasten notes
```

---

## Usage

### Pane Controls and Smaller Windows

| Header control | Location | Action |
|---|---|---|
| Sidebar icon | Far left, before New document | Show or hide Files/Notebook |
| **AI** button | Near the right, beside the menu | Show or hide the AI assistant |
| Menu (three horizontal lines) | Near the right | Save All, Save As, Save Version, Find, Replace, Export, Recover Document, and theme toggle |

The editor keeps priority as the window shrinks:

- Above 1180 logical pixels, both panes appear beside the editor.
- At 1180 or less, the AI pane hides first.
- At 820 or less, Files/Notebook also hides.

The thresholds follow system text scaling. Use the header buttons to reopen hidden panes as drawers over the editor. At narrow widths, opening one drawer closes the other. Opening a file or note closes the Files/Notebook drawer so you can start editing. Widening the window restores the panes beside the editor, respecting any pane you manually hid while it was docked.

Resizing preserves open tabs, unsaved text, chat history, and an unsent instruction. The formatting toolbar scrolls horizontally when space is limited. The assistant uses full-width actions and wrapping explanations. New, Open, and Save use icons with tooltips; Export and Recover are in the header menu.

### Opening Documents
- **File browser** (left sidebar) — double-click any file in the workspace tree
- **Open document icon** — file dialog with filter for all supported formats

### Editing
- **Formatting toolbar** — click H1/H2/H3 for headings, B/I for bold/italic, etc.
- **Preview** — click Preview for a full, scrollable, read-only Markdown view of the current document. Links open in your browser when clicked; images appear as labels without loading remote resources.
- **Edit selection…** — select text, type an instruction in the AI pane, then click this toolbar action; it also opens the AI pane if hidden

### Using the Assistant

The assistant has its model controls at the top, conversation in the middle, and task controls at the bottom. Choose an installed **Local AI model**, then select a task under **What would you like help with?** The explanation describes the result, and the context line shows which part of your document is used. For writing tasks, type an instruction and click the action button or press Enter. For evidence checks, highlight a passage, choose source collections, and click **Check claims & sources**; an instruction is not needed.

| Task | Context and result |
|---|---|
| **Ask about my document** | Uses the current document and recent conversation; answers in the conversation. |
| **Improve selected text** | Uses highlighted text with document context; shows a replacement for approval before changing the text. |
| **Continue writing** | Uses the selected passage or last 25 lines before the cursor; suggests 2–4 sentences for approval before insertion. An instruction is optional. |
| **Create a revised copy** | Uses the document, your instruction and recent conversation; opens a separate revised document in a new tab. |
| **Check claims & sources** | Uses highlighted text or up to 6,000 characters before the cursor; searches selected scholarly collections and saves a separate evidence report. |

**Clear conversation** clears the displayed conversation and its context for future writing requests. If a request is running, it also stops that request.

### Checking Claims Against Sources

1. Select **Check claims & sources** from the task dropdown at the bottom of the assistant, then highlight a passage. Without a selection, Co-Writer checks up to the last 6,000 characters before the cursor. The **Checking:** line shows the scope.
2. Click the caret beside **Source collections** below the **Checking:** line to choose where to search. This menu appears only while **Check claims & sources** is selected. Choices are remembered locally.
3. Click **Check claims & sources**. Co-Writer finds up to five statements locally, searches for evidence, then assesses the retrieved publication metadata and available abstracts.
4. Read the separate `evidence_audit_*.md` tab, or click **Open latest evidence report** for a formatted preview with clickable source links. Previous reports remain in **Versions**.

Switching between writing and checking tasks preserves any instruction you typed. The instruction box is hidden during evidence checks because those use the editor passage directly.

| Collection | Coverage |
|---|---|
| [Europe PMC](https://europepmc.org/RestfulWebService) | Biomedical and life science literature. |
| [arXiv](https://info.arxiv.org/help/api/user-manual.html) | Physics, mathematics, computing and other preprints/manuscripts. |
| [OpenAlex](https://help.openalex.org/api/) | Scholarly publications across disciplines. Basic searches use the keyless API budget. |

All three are selected by default. Each query retrieves up to four publications per collection. arXiv requests run one at a time and are spaced at least three seconds apart, including retries. Rate limits or outages are recorded in the report; results from available collections are retained. If every collection fails, the report records those failures rather than treating them as evidence against a claim. No accounts or new dependencies are needed for these searches.

Evidence audits keep the full draft on your computer. The local model separates lived experience, research claims, clinical interpretations, and legal claims. Only short scholarly search queries, capped at 12 words and 200 characters, are sent to the selected collections. The model is instructed to omit identifying details from queries; review sensitive passages before using online search. Lived experience and legal claims are not sent to scholarly indexes. Legal claims require current jurisdiction-specific sources.

Each audit retains confidence explanations, population and applicability notes, safer wording, limitations, and a deterministic claim-to-source record. The record adds search coverage, collection provenance, preprint flags and available retraction flags. Duplicate publications across collections are merged per claim. arXiv entries are treated as preprints/manuscripts even when a journal reference is supplied; peer review is not independently verified. This is an assessment of metadata and available abstracts, not an automatic full-text review. Open the linked publications to evaluate their evidence. Results are research aids rather than guarantees of correctness.

The activity row stays visible below the editor even when the AI pane is hidden. **Stop** cancels the current chat, edit, continuation, recovery, or research operation. Partial chat text already displayed remains visible; cancelled output is not applied as an edit or added to completed chat history. An in-flight network request may take time to finish closing, but its result is ignored. Only one AI operation runs at a time.

### Saving, Recovery, and Workspace Memory

A dot beside a tab name means its text has changed. **Autosaved · unsaved** means a recovery copy exists; use **Save** to write the original text document. Closing a changed tab or quitting offers **Save**, **Discard**, or **Cancel**. A failed save keeps the tab open and its changes intact.

Edited imports such as PDF, DOCX, and ODT use **Save As** to create a `.md` or `.txt` document; use **Export** for other output formats. If the original file changed elsewhere, Save also offers Save As to preserve the external version.

On reopening, Co-Writer restores existing tabs, cursor positions, window size, and pane preferences. If an unsaved recovery copy is available, choose **Restore**, **Discard Recovery**, or **Later**. Restore loads the recovered text into the editor without changing the original file. Each original path has a distinct recovery copy, including documents with the same filename in different directories.

Window and tab state lives in `~/.local/share/cowriter/session.json`. Recovery copies live in `~/.local/share/cowriter/workspace/autosaves/` as private `.draft.json` files. These files contain local document paths and draft text, respectively, and are excluded from Git along with other user data. Save your open drafts before restarting from an older version; older `.autosave.md` copies can still be opened through the file dialog.

### Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| Ctrl+N / Ctrl+O / Ctrl+S | New / Open / Save |
| Ctrl+Shift+S | Save As |
| Ctrl+Alt+S | Save All changed tabs |
| Ctrl+W / Ctrl+Q | Close tab / Quit, with save protection |
| Ctrl+F / Ctrl+H | Find / Find and Replace |
| Ctrl+G / Ctrl+Shift+G | Next / Previous match, wrapping at the document ends |
| F9 / Shift+F9 | Toggle Files/Notebook / AI |
| Ctrl+Shift+P | Full Markdown preview |
| Escape in the search bar | Close search and return focus to the editor |

Search treats the query as literal text. Use **Match case** when capitalization matters. **Replace** changes the selected match; when no match is selected, it selects the next one first. **Replace All** changes all matches in the current document and can be undone in one step.

### Notebook
- **+** beside Notebook — creates a new note in the notebook directory
- **Search** — type to filter notes by title or content
- **`[[links]]`** — type `[[note name]]` in any document to organize related notes

### Recovery
1. Choose **Recover Document…** from the header menu
2. Select the corrupt file
3. The LLM analyzes raw bytes and reconstructs readable content
4. Result opens as a new recovered tab

### Export
1. Choose **Export…** from the header menu
2. Select desired format
3. Choose save location

---

## Ubuntu/Debian Package Building

```bash
# Install build deps
sudo apt-get install debhelper dh-python python3-all python3-build \
  python3-setuptools python3-requests python3-markdown-it python3-gi \
  gir1.2-gtk-4.0 gir1.2-adw-1 python3-reportlab python3-docx python3-odf \
  python3-pypdf python3-striprtf

# Build
dpkg-buildpackage -us -uc -b

# Install
sudo dpkg -i ../cowriter_*.deb
sudo apt-get install -f
```

See [PACKAGING.md](PACKAGING.md) for full details.

---

## Development Checks

```bash
python3 -m unittest discover -s tests -v
```

The GTK tests require a display and open temporary test windows with isolated data and mocked networking. They check pane priority, drawer controls, resizing, save failures and close prompts, draft recovery, workspace restoration, Unicode search and undo, full preview, background model discovery, and cancelled AI responses. These tests skip when a display is unavailable; the helper, workspace, preview, and research tests still run.

---

## License

MIT — see [LICENSE](LICENSE)

All optional dependencies (reportlab, pypdf, python-docx, odfpy, striprtf, mobi) are MIT/BSD/Apache 2.0 licensed. No GPL restrictions.
