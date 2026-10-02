# Co-Writer — Ubuntu/GNOME Native Packaging Guide

This document describes how to build and install Co-Writer as a native Ubuntu application.

## Quick Install (Recommended)

```bash
./install.sh
```

This installs into `~/.local/` — no sudo needed. Launch from your applications menu as "Co-Writer" or run `cowriter-gui` from terminal.

## Quick Uninstall

```bash
./uninstall.sh
```

## Package Structure

```
co-writer/
├── src/cowriter/           # Python package source
│   ├── __init__.py
│   ├── gtk_app.py          # Main GTK4 application
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

Install build dependencies:

```bash
sudo apt-get update
sudo apt-get install -y \
    debhelper \
    dh-python \
    python3-all \
    python3-setuptools \
    python3-requests \
    python3-gi \
    gir1.2-gtk-4.0 \
    gir1.2-adw-1 \
    python3-build
```

## Building the Package

### Quick Build

```bash
./build-package.sh
```

### Manual Build

1. **Build Python wheel** (optional, for testing):
   ```bash
   python3 -m build --wheel
   ```

2. **Build Debian package**:
   ```bash
   dpkg-buildpackage -us -uc -b
   ```

   The `.deb` file will be created in the parent directory.

## Installation

```bash
sudo dpkg -i ../cowriter_*.deb
sudo apt-get install -f  # Fix any missing dependencies
```

## Running the Application

After installation:

- **GUI launcher**: `cowriter-gui` (or find "Co-Writer" in your application menu)
- **Console launcher**: `cowriter`

## Data Locations

The application stores user data in:

- **Workspace**: `~/.local/share/cowriter/workspace/`
- **Autosaves**: `~/.local/share/cowriter/workspace/autosaves/`
- **Versions**: `~/.local/share/cowriter/workspace/versions/`
- **Custom soul prompt**: `~/.local/share/cowriter/soul.md`

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
dpkg -c ../cowriter_*.deb

# Check package info
dpkg -I ../cowriter_*.deb

# Lint the package
lintian ../cowriter_*.deb
```

## Dependencies

- **Runtime**: python3, python3-requests, python3-gi, GTK 4.10+ (`gir1.2-gtk-4.0`), libadwaita 1.4+ (`gir1.2-adw-1`)
- **Optional editor support**: GtkSourceView 5 (`gir1.2-gtksource-5`) for syntax highlighting and line numbers
- **Recommended**: ollama (for AI features)
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

## Notes

- The application requires Ollama to be running for AI features
- User data is stored in `~/.local/share/cowriter/` (XDG Base Directory compliant)
- The package is architecture-independent (all Python)
