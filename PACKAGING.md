# Co-Writer — Ubuntu/GNOME Native Packaging Guide

This document describes how to build and install Co-Writer as a native Ubuntu application.

## Debian/Ubuntu Installer (Recommended)

Download `cowriter_4.1.0-1_all.deb` and `SHA256SUMS` from the [4.1.0 release](https://github.com/chukrobertson/co-writer/releases/tag/v4.1.0). In the download directory:

```bash
sha256sum -c SHA256SUMS
sudo apt install ./cowriter_4.1.0-1_all.deb
```

Launch **Co-Writer** from the applications menu or run `cowriter-gui`. The package is architecture-independent and requires your distribution to provide GTK 4.10+, libadwaita 1.4+, and Python 3.9+. APT installs runtime dependencies, including Aspell's English dictionary. Ollama is optional and only needed for the AI features.

Use the same `apt install ./...deb` command for upgrades. Package removal preserves drafts, preferences, dictionaries, and craft notes. If moving from a source installation, run that checkout's `./uninstall.sh` first to remove the user launcher that could shadow `/usr/bin/cowriter-gui`; it preserves your data.

## Source Install

```bash
./install.sh
```

This installs into `~/.local/` — no sudo needed. Launch from your applications menu as "Co-Writer" or run `cowriter-gui` from terminal.

## Source Uninstall

```bash
./uninstall.sh
```

## Package Structure

```
co-writer/
├── src/cowriter/           # Python package source
│   ├── __init__.py
│   ├── gtk_app.py          # Main GTK4 application
│   ├── workspace.py        # Atomic saves and private recovery copies
│   ├── preview.py          # Native Markdown preview
│   ├── proofreading.py     # Offline spelling and common English grammar rules
│   ├── gtk_proofreading.py # Editor underlines and explicit corrections
│   ├── poetry.py           # Offline pronunciation, rhythm and rhyme lookup
│   ├── gtk_poetry.py       # Optional poetry workbench and editor colors
│   ├── craft.py            # Manual readings, rhyme maps and private craft notes
│   ├── gtk_craft.py        # Writer-controlled craft views and reference cards
│   ├── poetry_data/        # Bundled CMU pronunciation dictionary and its license
│   ├── jobs.py             # AI cancellation
│   ├── research.py         # Scholarly evidence lookup
│   ├── exporting.py        # Formatted office, HTML and paginated PDF copies
│   ├── desktop.py          # Writer and desktop mail handoffs
│   ├── __main__.py         # `python -m cowriter` entry point and legacy UI
│   └── soul.md             # AI system prompt
├── data/                   # Desktop integration files
│   ├── com.github.chukrobertson.cowriter.desktop    # GNOME desktop entry
│   ├── com.github.chukrobertson.cowriter.svg        # Application icon
│   └── com.github.chukrobertson.cowriter.metainfo.xml  # AppStream metadata
├── debian/                 # Debian packaging files
│   ├── changelog
│   ├── control
│   ├── copyright
│   ├── install
│   ├── rules
│   └── source/format
├── pyproject.toml          # Python package configuration
└── build-package.sh        # Build script
```

## Prerequisites

The maintained GUI requires GTK 4.10 or newer, libadwaita 1.4 or newer, and PyGObject. File dialogs require GTK 4.10; adaptive panes use libadwaita's split views and breakpoints.

Offline English spelling uses `aspell` and `aspell-en`, installed automatically as Debian runtime dependencies. For a source/pip installation, install these system packages separately. Without them the editor shows **Check limited**, while the built-in grammar rules continue to work. Proofreading never requires a network service or AI model.

Poetry tools include a compressed copy of the CMU English pronunciation dictionary as Python package data, together with its license and pinned source provenance. Wheels and Debian packages must retain `cowriter/poetry_data/*`. Poetry analysis and rhyme lookup need no additional system package or runtime download; Aspell only improves the order of familiar rhyme suggestions. See `src/cowriter/poetry_data/CMUDICT-LICENSE` and `debian/copyright` for the bundled data's redistribution terms.

Manual readings, motifs, rhyme labels, section bookmarks, and pass notes use private JSON sidecars under `~/.local/share/cowriter/poetry-notes/`. These are runtime user data and must not be packaged or included in manuscript exports. The craft views and fixed reference cards require no additional dependency or AI service.

Install build dependencies:

```bash
sudo apt-get update
sudo apt-get install -y \
    debhelper \
    dh-python \
    pybuild-plugin-pyproject \
    python3-all \
    python3-setuptools \
    python3-wheel \
    python3-requests \
    python3-markdown-it \
    python3-gi \
    gir1.2-gtk-4.0 \
    gir1.2-adw-1 \
    python3-reportlab \
    python3-docx \
    python3-odf \
    python3-pypdf \
    python3-striprtf \
    python3-build \
    aspell aspell-en
```

## Building the Package

### Quick Build

```bash
./build-package.sh
```

The script checks Debian build dependencies and builds with PEP 517 in a temporary copy of the source. It leaves the development checkout intact. `dist/` receives `cowriter_4.1.0-1_all.deb`, the `.buildinfo` and `.changes` records, and `SHA256SUMS`. Build outputs are ignored by Git; publish installers as GitHub release assets.

An isolated builder that already provides the dependencies outside dpkg's package database can use `./build-package.sh --no-check-builddeps`. This passes `-d` to `dpkg-buildpackage`; it does not install or supply any dependencies. The normal build should use the dependency check.

### Manual Build

1. **Build Python wheel** (optional, for testing):
   ```bash
   python3 -m build --wheel
   ```

2. **Build Debian package**:
   ```bash
   dpkg-buildpackage -us -uc -b
   ```

   For this manual command, the `.deb` file is created in the parent directory. Prefer the script above for an isolated build and checksums.

## Installation

```bash
sudo apt install ./dist/cowriter_4.1.0-1_all.deb
```

## Running the Application

After installation:

- **GUI launcher**: `cowriter-gui` (or find "Co-Writer" in your application menu)
- **Console launcher**: `cowriter`

## Data Locations

The application stores user data in:

- **Workspace**: `~/.local/share/cowriter/workspace/`
- **Autosaves**: `~/.local/share/cowriter/workspace/autosaves/`
- **Workspace memory**: `~/.local/share/cowriter/session.json` (window size, open document paths, cursors, and pane preferences)
- **Versions**: `~/.local/share/cowriter/workspace/versions/`
- **Shared copies**: `~/.local/share/cowriter/workspace/shared/` (office, PDF, email attachments, and revised imports)
- **Custom soul prompt**: `~/.local/share/cowriter/soul.md`
- **Preferences**: `~/.local/share/cowriter/config.json` (model, theme and source collection choices)

Session state and recovery copies contain private document paths and text. They remain local, use private file permissions, and are excluded from Git. The native preview does not fetch remote images.

Shared copies also contain user document text, remain local, and are excluded from Git and package contents. They persist so external editors and mail drafts can keep using them. Users can remove them through **Share & open → Show shared copies in Files** when finished. Exported HTML and office/PDF copies do not fetch remote images.

Evidence checks use the existing Requests dependency to query Europe PMC, arXiv and OpenAlex; they add no package dependencies. These services receive short scholarly search queries. Evidence reports stay in the local versions directory and are not included in packages. See [Checking Claims Against Sources](README.md#checking-claims-against-sources) for coverage and controls.

## Uninstallation

```bash
sudo apt-get remove cowriter
```

To remove user data:

```bash
rm -rf ~/.local/share/cowriter
```

## Package Maintenance

### Updating the Version

1. Update version in `pyproject.toml`
2. Update version in `src/cowriter/__init__.py`
3. Add entry to `debian/changelog`:
   ```bash
   dch -i  # or dch -v <version>-1
   ```
4. Update release date in `data/com.github.chukrobertson.cowriter.metainfo.xml`

### Testing the Package

```bash
# Check package contents
dpkg-deb --contents dist/cowriter_4.1.0-1_all.deb

# Check package info
dpkg-deb --info dist/cowriter_4.1.0-1_all.deb

# Lint the package
lintian dist/cowriter_4.1.0-1_all.deb
```

The Debian build explicitly runs unittest discovery in `tests/` against its built Python package. GTK checks require an accessible display and D-Bus session; they skip on a headless builder. For release validation, also run the full suite with a display and smoke-test the extracted installer in an isolated home directory. Verify that the launcher, desktop files, all craft modules, dictionary, license, and provenance are present and that no runtime user data is included.

## Publishing a Release

Update `pyproject.toml`, `src/cowriter/__init__.py`, `debian/changelog`, AppStream release metadata, `CHANGELOG.md`, and the installer links in this guide and README together. Build and verify the package before committing and pushing the release source. Create a tag for that commit (for example, `v4.1.0`), then publish a GitHub release with the `.deb` and `SHA256SUMS` from `dist/`. Keep the installer out of the source repository.

## Dependencies

- **Runtime**: python3, python3-requests, python3-markdown-it, python3-gi, GTK 4.10+ (`gir1.2-gtk-4.0`), libadwaita 1.4+ (`gir1.2-adw-1`)
- **Optional editor support**: GtkSourceView 5 (`gir1.2-gtksource-5`) for syntax highlighting and line numbers
- **Recommended**: ollama (for AI features)
- **Optional desktop applications**: LibreOffice Writer (`libreoffice-writer`), a default mail client such as Thunderbird, and a PDF viewer/file manager
- **Optional email fallback**: `xdg-utils` supplies `xdg-email` when the desktop email portal is unavailable; no extra Python dependency is needed
- **Import/Export formats**:
  - python3-reportlab (PDF export)
  - python3-docx (DOCX import/export)
  - python3-odf (ODT import/export)
  - python3-pypdf (PDF import)
  - python3-striprtf (RTF import)
  - python3-mobi (MOBI import, via pip)

## Desktop Integration

The package includes:

- **Desktop entry**: Integrates with GNOME application menu
- **AppStream metadata**: Provides app information for software centers
- **Icon**: SVG icon in hicolor theme

The **Share & open** menu creates formatted ODT copies for Writer, PDF copies for the default viewer, Markdown copies for an application chooser, and email drafts with selected text or a document attachment. Files shortcuts use GTK's native file launcher. Email uses the freedesktop desktop portal with file-descriptor attachments and an `xdg-email` fallback. It opens a composer for human review and never sends messages. Importing a revised office copy creates a new Markdown tab and preserves its source; this supports basic text formatting rather than a lossless office-document round trip.

## Notes

- The application requires Ollama to be running for AI features
- User data is stored in `~/.local/share/cowriter/` (XDG Base Directory compliant)
- The package is architecture-independent (all Python)
