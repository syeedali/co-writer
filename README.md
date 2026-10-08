# Co-Writer 4.1

Local research and writing companion for the desktop, with **Documancy** for opening, editing, reformatting, and recovering documents. Built for Ubuntu/GNOME with local AI via [Ollama](https://ollama.com).

<p align="center">
  <strong>Open · Edit · Recover · Export · AI</strong>
</p>

---

## Features

### 📂 Documancy
- **Multi-tab editor** — open and work on multiple documents simultaneously
- **Private proofreading** — red spelling underlines and blue underlines for common English grammar slips, with correction suggestions and a personal dictionary
- **Poetry & prose tools** — rhythm colors, syllable counts, offline rhymes, personal reading marks, rhyme maps, repetitions, reference cards, and private craft notes
- **9 import formats** — TXT, MD, HTML, PDF, DOCX, ODT, EPUB, MOBI, RTF
- **6 export formats** — TXT, MD, HTML, PDF, DOCX, ODT
- **Share & open** — formatted Writer copies, PDF review, mail composition, Files shortcuts, and importing revisions into a new tab
- **Open Pressroom handoff** — send an article copy with its linked evidence reports for publishing
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

### Debian/Ubuntu Installer (Recommended)

Download [cowriter_4.1.0-1_all.deb](https://github.com/chukrobertson/co-writer/releases/download/v4.1.0/cowriter_4.1.0-1_all.deb) from the [4.1.0 release](https://github.com/chukrobertson/co-writer/releases/tag/v4.1.0), then run from your download directory:

```bash
sudo apt install ./cowriter_4.1.0-1_all.deb
```

APT installs the required GTK, Python, and offline spelling packages. The installer requires GTK 4.10+ and libadwaita 1.4+ from your distribution. Launch **Co-Writer** from the applications menu or run `cowriter-gui`. Ollama is optional; proofreading and poetry tools work without it.

The release also includes `SHA256SUMS`. Download it beside the installer and verify with `sha256sum -c SHA256SUMS` before installing. Install a newer `.deb` with the same command to upgrade; your local drafts and settings are retained.

If you previously used the source installer, its `~/.local/bin` launcher can take priority over `/usr/bin/cowriter-gui`. Run `./uninstall.sh` from that checkout before switching to the `.deb`; the uninstaller leaves your user data in place.

### Install from Source

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

For a Debian package installation:

```bash
sudo apt remove cowriter
```

For a source installation:

```bash
./uninstall.sh
```

---

## Requirements

| Requirement | Package | Notes |
|---|---|---|
| Python 3.9+ | `python3` | |
| GTK 4.10+ + libadwaita 1.4+ | `gir1.2-gtk-4.0`, `gir1.2-adw-1` | Required for file dialogs and adaptive panes |
| PyGObject | `python3-gi` | Python bindings for GTK and libadwaita |
| GtkSourceView 5 | `gir1.2-gtksource-5` | Optional syntax highlighting and line numbers |
| English spelling dictionary | `aspell`, `aspell-en` | Local spelling checks and suggestions; included as Debian package dependencies |
| Requests | `python3-requests` | Required for Ollama |
| Markdown parser | `python3-markdown-it` / `markdown-it-py` | Required for the native Markdown preview; pip installs it with the app |
| **Ollama** | [ollama.com](https://ollama.com) | For AI features (optional, UI works without) |
| Internet connection | — | Only required for scholarly fact-check searches |
| LibreOffice Writer | `libreoffice-writer` | Optional; opens formatted ODT copies |
| Default mail application | Thunderbird or another desktop mail app | Optional; email actions open a compose window for you to review |
| Desktop email fallback | `xdg-utils` | Optional; provides `xdg-email` when the desktop email portal is unavailable |

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
            ├── shared/       # Private office, PDF, email, and revised copies
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

### Spelling & Grammar

Proofreading is on by default in every document and note. After a short pause in typing, **red wavy underlines** mark possible misspellings and **blue wavy underlines** mark common grammar slips. Click an underlined word for suggestions, hover for an explanation, or press **F7** to visit the next issue. Choosing a correction is one undoable edit; text is never corrected automatically. The bottom bar shows the issue count and opens the next suggestion when clicked.

English grammar checks cover missing apostrophes in common contractions (`dont` → `don't`, `Im` → `I'm`), lowercase `i` and its contractions, accidentally repeated words, and a few simple subject–verb agreement errors. These are focused mechanical checks, not a comprehensive grammar or style review. Ambiguous valid words such as `its`, `were`, and `well` are left alone. Code blocks, inline code, URLs, email addresses, and Markdown link destinations are excluded; link labels are checked.

Use **Ignore in this document** for intentional wording during the current tab session. **Add to personal dictionary** remembers names and specialist words across documents and restarts, locally in `~/.local/share/cowriter/proofreading-words.json`. **Document menu → Spelling & grammar** toggles checking for all tabs and remembers your preference.

All proofreading runs locally using Aspell and built-in English rules, with no AI model or network request. The Debian package installs `aspell` and `aspell-en`; for a source/pip installation, install them with `sudo apt-get install aspell aspell-en`. If spelling is unavailable, the status reads **Check limited** and its tooltip explains what to install; grammar checks continue working.

### Poetry & Prose

Open **Poetry…** on the formatting toolbar, **Document menu → Poetry & prose…**, or press **Ctrl+Alt+P**. A separate, nonmodal window stays beside your writing and follows the active document. It starts with the current stanza or paragraph; choose **Selected text** or **Whole document** for a different scope. Large passages show an explicitly labeled excerpt (up to 24,000 characters and 100 displayed lines); select a smaller passage to explore beyond it.

**Rhythm & lines** shows syllable counts and one possible dictionary stress pattern for each line: `·` soft, `●` strong, `◐` secondary stress, and `?` unknown stress. Alternate pronunciations retain their syllable ranges—`fire`, for example, can have one or two syllables. Unknown words receive visibly estimated counts (`≈`) without invented stresses. Click a line to locate it in the editor, or hover an editor word for its possible readings.

Turn on **Rhythm colors** to shade soft words green, strong words amber, words with mixed stress violet, and unknown or estimated stresses gray. **Rhyme colors** gives matching line endings the same shade and lists their rhyme groups. Group numbers distinguish families when the six-color palette repeats. End-rhyme colors use the first dictionary pronunciation; hover ambiguous words to see other readings. Repeating the same word alone does not form a rhyme group. Colors coexist with spelling underlines, affect only the explored passage, and clear when you close the tools.

**Find rhymes** looks up a typed word or a word selected in the editor. It separates matching end sounds from looser **Vowel echoes**, and shows up to 60 suggestions in each group. Click a suggestion to copy it, then paste wherever you like. The tools do not change your writing automatically. All lookups and analysis run locally, with no AI model, network service, or extra download at runtime.

Use the tool chooser at the top of the window to open the additional craft views. The passage selector applies to rhythm, rhyme mapping, repetitions, and your reading. **Find rhymes** also offers an optional syllable-count filter (one through eight syllables); alternate pronunciations are considered before the 60-result limit.

- **Rhyme map** connects endings across intervening lines and separates possible rhymes, vowel echoes, and repeated endings. Choose any two lines to remember your own **Rhyme**, **Loose rhyme**, or **Intentional gap** label. These labels are private annotations; the map does not score unpaired lines. Up to 80 connections are displayed, with your choices first.
- **Repetitions** finds recurring words, two-word phrases, or three-word phrases. Include everyday words when useful, or search for a particular phrase. Expand a result to visit its occurrences, temporarily highlight them, or remember it as a motif. The view shows up to 40 groups and 100 occurrences per group. Repetition is treated as a writing choice.
- **My reading** lets you choose a complete line, adjust syllable counts, cycle each syllable's stress, and mark short (`|`) or long (`||`) pauses after words. Your choices update the rhythm display and colors. **Return this line to dictionary hints** clears the personal reading. For long prose lines, the first 60 words have manual controls; other words retain their dictionary hints. Partial-line selections can be explored but cannot receive saved line readings.
- **Reference cards** contains short, fixed examples of iambic pentameter, rhyming couplets, accentual verse, end-stopping and enjambment, and loose sound connections. The examples are provided as references and never inserted into your manuscript.
- **My notes** keeps a **This pass** question, a private note, and named section bookmarks. Notes save after a short pause, when switching documents, and on closing. **Save notes now** retries a failed write. Bookmarks navigate to their original lines without adding section headings to the poem.

Craft annotations are private JSON sidecars in `~/.local/share/cowriter/poetry-notes/`, with separate records for each source path and private file permissions. They stay out of manuscript saves, exports, and Open Pressroom handoffs. Save As carries the notes to the new path when it has no existing note record; the original notes are retained. Unchanged unique lines can move without losing their readings or bookmarks. Edited or ambiguous lines leave their annotations aside instead of applying them to different words; My notes reports held readings and disabled bookmarks. All of these tools operate without AI generation.

The bundled [CMU Pronouncing Dictionary](https://github.com/cmusphinx/cmudict) supplies English pronunciations, including names and uncommon words. Aspell, when available, helps bring familiar vocabulary first. These are dictionary sound hints: dialect, spoken emphasis, elision, and your own reading can change the rhythm. They do not grade a poem or require a particular meter. Code and link destinations are excluded just as they are in proofreading. Dictionary provenance and redistribution terms are included in `src/cowriter/poetry_data/`.

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
| F7 | Next spelling or grammar issue, with correction options |
| Ctrl+Alt+P | Open Poetry & prose tools |
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
2. Name the copy with a `.md`, `.txt`, `.html`, `.pdf`, `.docx`, or `.odt` extension
3. Choose the save location

ODT, DOCX, HTML, and PDF exports format Markdown headings, lists, emphasis, code, tables, and source links. PDFs wrap text across pages and include page numbers. Markdown and text exports retain the editor's original text. Remote images are represented by descriptions; exports do not download them. Exporting runs in the background and keeps the editor available. A failed export preserves any existing destination file.

### Share & Open with Desktop Applications

Open the header menu and choose **Share & open**:

| Action | What happens |
|---|---|
| **Open formatted copy in Writer** | Creates a separate editable ODT from the current tab, including unsaved edits, then opens LibreOffice Writer. |
| **Export PDF & open** | Creates a PDF copy and opens your default PDF viewer, such as GNOME Document Viewer. |
| **Open Markdown copy with…** | Creates a Markdown copy and asks which application should open it. |
| **Show current file in Files** | Reveals the current tab's original file in your file manager. Unsaved editor changes are not written to it. |
| **Show shared copies in Files** | Opens the folder containing the copies created by these actions. |
| **Compose email from selection** | Puts only highlighted text into your default mail composer's body. Markdown formatting becomes readable text, with source URLs retained. Select a passage first to enable this action. |
| **Email document as PDF / editable ODT** | Creates a copy of the entire current tab and attaches it to a new compose window. This also works with an evidence report tab. |
| **Import revised copy…** | Reads a revised document and creates a separate Markdown tab, preserving both the external file and your original draft. |

Email uses the desktop email portal, with `xdg-email` as a fallback. Set Thunderbird or your preferred mail application as the default in Ubuntu's application settings. Co-Writer does not send email or choose recipients; review and send from your mail app. Source links in the document preview already open in your default browser.

To revise in Writer: open the formatted copy, edit and save it in Writer, then use **Import revised copy…** and choose that saved ODT. Office imports retain text and basic headings, emphasis, links, and tables. Comments, tracked changes, images, and page layout are not preserved as an office-document round trip; keep the original office file for those features.

Shared copies remain locally in `~/.local/share/cowriter/workspace/shared/` so mail attachments and external editors can keep using them. They use private file permissions and are excluded from Git and packages. They are not deleted automatically; use **Show shared copies in Files** to remove copies you no longer need after closing their external documents and mail drafts. Opening or composing passes the chosen content to the application you selected.

---

## Ubuntu/Debian Package Building

```bash
# Install build deps
sudo apt-get install debhelper dh-python pybuild-plugin-pyproject python3-all python3-build \
  python3-setuptools python3-wheel python3-requests python3-markdown-it python3-gi \
  gir1.2-gtk-4.0 gir1.2-adw-1 python3-reportlab python3-docx python3-odf \
  python3-pypdf python3-striprtf aspell aspell-en

# Build
./build-package.sh

# Install
sudo apt install ./dist/cowriter_4.1.0-1_all.deb
```

The build runs in a temporary source copy and writes the installer, build records, and `SHA256SUMS` to `dist/`. See [PACKAGING.md](PACKAGING.md) for full details and [CHANGELOG.md](CHANGELOG.md) for release notes.

---

## Development Checks

```bash
python3 -m unittest discover -s tests -v
```

The GTK tests require a display and open temporary test windows with isolated data and mocked networking. They check pane priority, drawer controls, resizing, save failures and close prompts, draft recovery, workspace restoration, Unicode search and undo, full preview, background model discovery, cancelled AI responses, desktop handoffs that preserve drafts, and proofreading underlines, corrections, stale results, and personal dictionaries. Install `aspell` and `aspell-en` for the complete proofreading integration checks. GTK tests skip when a display is unavailable; helper, workspace, preview, research, export, and proofreading-rule checks still run. Desktop tests mock external application launches and never send email.

---

## License

MIT — see [LICENSE](LICENSE)

All optional dependencies (reportlab, pypdf, python-docx, odfpy, striprtf, mobi) are MIT/BSD/Apache 2.0 licensed. No GPL restrictions.


### Send a researched article to Open Pressroom

From the article tab, use **Document menu → Share & open → Send article to Open Pressroom**. It sends a private local copy of the current editor text and up to ten linked evidence reviews, including original draft/passage snapshots, scope, assessments, source metadata, and coverage. Unsaved edits are included; the original document is unchanged. New evidence checks are linked to their originating article and follow Save As. Use **Attach evidence report to article…** for an older Co-Writer Evidence Audit report; its original review context is recorded as unknown.

Open Pressroom opens the article in Stories, with a digital chapter and a Research & sources view. It warns about changed drafts and keeps internal reports out of article/digital exports. Inline Markdown citation/link tokens stay editable text in the first pass. Build `open-pressroom-native` in the sibling `openpressroom/native` checkout, install it on PATH, or set `OPEN_PRESSROOM_EXECUTABLE` to the executable path. If launch fails, the saved `.cowriter-article.json` copy can be imported using Open Pressroom's Import Co-Writer button. Transfer limits are 1 MB of article text and 8 MiB total. Each send creates a separate copy; it does not publish to Substack or synchronize subsequent edits.
