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
- **Quick preview** — inspect the current document without leaving the editor

### 🤖 AI Assistant (Ollama)
- **Model auto-detection** — automatically finds your installed Ollama models
- **Configurable model selector** — switch models from the UI, persisted across sessions
- **Chat interface** — ask questions, get feedback, request rewrites
- **Edit selection** — select text, give an instruction, accept or reject the AI edit
- **Generate draft** — produce a full revised document from chat context
- **Help me write** — preview a 2-4 sentence continuation after selected text, or at the cursor when nothing is selected
- **Research** — separate lived experience from research, clinical, and legal claims; review evidence-linked findings

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
- **Version snapshots** — save timestamped versions of any document
- **Dark/light theme** — toggle persisted in config
- **Config persistence** — model choice and theme saved to `~/.local/share/cowriter/config.json`

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
| Menu (three horizontal lines) | Near the right | Save All, Save Version, Export, Recover Document, and theme toggle |

The editor keeps priority as the window shrinks:

- Above 1180 logical pixels, both panes appear beside the editor.
- At 1180 or less, the AI pane hides first.
- At 820 or less, Files/Notebook also hides.

The thresholds follow system text scaling. Use the header buttons to reopen hidden panes as drawers over the editor. At narrow widths, opening one drawer closes the other. Opening a file or note closes the Files/Notebook drawer so you can start editing. Widening the window restores the panes beside the editor.

Resizing preserves open tabs, unsaved text, chat history, and an unsent instruction. The formatting toolbar scrolls horizontally when space is limited, and AI action buttons wrap into rows. New, Open, and Save use icons with tooltips; Export and Recover are in the header menu.

### Opening Documents
- **File browser** (left sidebar) — double-click any file in the workspace tree
- **Open document icon** — file dialog with filter for all supported formats

### Editing
- **Formatting toolbar** — click H1/H2/H3 for headings, B/I for bold/italic, etc.
- **Preview** — click Preview for a quick read-only view of the current document
- **Edit with AI** — select text, type an instruction in the AI pane, then click **AI Edit** in the formatting toolbar; this also opens the AI pane if it is hidden
- **Continue** — select a passage to continue it after the selection; without a selection, Continue uses the text before the cursor
- **Research** — select a passage (or place the cursor after it) to classify its claims and search Europe PMC for supporting or conflicting research

Evidence audits keep the draft on your computer. The local model separates lived experience, research claims, clinical interpretations, and legal claims. Only short scholarly search terms are sent to Europe PMC. Each audit is saved as Markdown with confidence explanations, population and applicability notes, safer wording, study-design context, limitations, and a deterministic claim-to-source record. Results are research aids rather than medical or legal advice or guarantees of correctness.

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

The GTK layout tests require a display and open temporary test windows with isolated data. They check pane priority, drawer controls, resizing from 480 to 1400 pixels, and preservation of draft and chat content. These tests skip when a display is unavailable; the helper and research tests still run.

---

## License

MIT — see [LICENSE](LICENSE)

All optional dependencies (reportlab, pypdf, python-docx, odfpy, striprtf, mobi) are MIT/BSD/Apache 2.0 licensed. No GPL restrictions.
