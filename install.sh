#!/bin/bash
set -e

echo "==================================="
echo "  Co-Writer — Native Installer"
echo "==================================="
echo ""

APP_NAME="cowriter"
APP_ID="com.github.chukrobertson.cowriter"
DISPLAY_NAME="Co-Writer"
INSTALL_DIR="${HOME}/.local"
APP_DIR="${INSTALL_DIR}/share/${APP_NAME}"
DESKTOP_DIR="${INSTALL_DIR}/share/applications"
ICON_DIR="${INSTALL_DIR}/share/icons/hicolor/scalable/apps"
METAINFO_DIR="${INSTALL_DIR}/share/metainfo"
BIN_DIR="${INSTALL_DIR}/bin"

MD_FILE="${INSTALL_DIR}/share/cowriter.md"

echo "[1/5] Checking dependencies..."
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found. Install with: sudo apt-get install python3"
    exit 1
fi

if ! python3 -c "import gi; gi.require_version('Gtk', '4.0'); from gi.repository import Gtk; print('OK')" 2>/dev/null; then
    echo "ERROR: GTK4 not found. Install with: sudo apt-get install gir1.2-gtk-4.0"
    exit 1
fi

if ! python3 -c "import gi; gi.require_version('Adw', '1'); from gi.repository import Adw; print('OK')" 2>/dev/null; then
    echo "ERROR: Adwaita not found. Install with: sudo apt-get install gir1.2-adw-1"
    exit 1
fi

if ! python3 -c "import requests" 2>/dev/null; then
    echo "WARNING: requests not installed. Install with: sudo apt-get install python3-requests"
fi

echo "[2/5] Installing Python package..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"
pip install -e . --break-system-packages 2>/dev/null || pip install -e . --user 2>/dev/null || pip install -e .

echo "[3/5] Installing desktop icons and files..."
mkdir -p "${DESKTOP_DIR}" "${ICON_DIR}" "${METAINFO_DIR}"

install -m 644 "data/${APP_ID}.svg" "${ICON_DIR}/${APP_ID}.svg"
install -m 644 "data/${APP_ID}.desktop" "${DESKTOP_DIR}/${APP_ID}.desktop"
# A direct icon path also works when a user's icon theme cache is stale.
python3 - "${DESKTOP_DIR}/${APP_ID}.desktop" "${ICON_DIR}/${APP_ID}.svg" <<'PY'
from pathlib import Path
import sys

desktop = Path(sys.argv[1])
icon = Path(sys.argv[2])
desktop.write_text(
    desktop.read_text(encoding="utf-8").replace(
        f"Icon={icon.stem}\n", f"Icon={icon}\n", 1
    ),
    encoding="utf-8",
)
PY
rm -f "${ICON_DIR}/cowriter.svg" "${DESKTOP_DIR}/cowriter.desktop"

if [ -f data/com.github.chukrobertson.cowriter.metainfo.xml ]; then
    install -m 644 data/com.github.chukrobertson.cowriter.metainfo.xml "${METAINFO_DIR}/com.github.chukrobertson.cowriter.metainfo.xml"
fi

echo "[4/5] Updating desktop database..."
update-desktop-database "${DESKTOP_DIR}" 2>/dev/null || echo "  (skipped — update-desktop-database not found)"

# GNOME favorites store desktop file names, so carry existing pins to the
# application-ID launcher when upgrading from older installs.
if [[ "${XDG_CURRENT_DESKTOP:-}" == *GNOME* ]]; then
    python3 - <<'PY' || echo "  (could not update the existing dock pin)"
from gi.repository import Gio

settings = Gio.Settings.new("org.gnome.shell")
favorites = settings.get_strv("favorite-apps")
if "cowriter.desktop" in favorites:
    updated = []
    for favorite in favorites:
        name = "com.github.chukrobertson.cowriter.desktop" if favorite == "cowriter.desktop" else favorite
        if name not in updated:
            updated.append(name)
    if not settings.set_strv("favorite-apps", updated):
        raise RuntimeError("GNOME did not save the updated dock pin")
PY
fi

# Create a marker file so we can find the install path later
mkdir -p "${APP_DIR}"
echo "installed=$(date -Iseconds)" > "${APP_DIR}/.installed"

echo "[5/5] Installing optional dependencies..."
for pkg in reportlab pypdf python-docx odfpy mobi striprtf; do
    python3 -c "import ${pkg//-/_}" 2>/dev/null && echo "  ✓ ${pkg} (already installed)" || {
        echo "  → Installing ${pkg}..."
        pip install "${pkg}" --break-system-packages 2>/dev/null || pip install "${pkg}" --user 2>/dev/null || true
    }
done

python3 -c "import gi; gi.require_version('GtkSource', '5'); from gi.repository import GtkSource; print('  ✓ GtkSourceView 5 (syntax highlighting)')" 2>/dev/null || {
    echo "  → For syntax highlighting: sudo apt-get install gir1.2-gtksource-5"
}

cat << "EOF"

===================================
  Co-Writer installed!
===================================

Launch from:
  • Applications menu → "Co-Writer"
  • Terminal: cowriter-gui

Data stored in: ~/.local/share/cowriter/

To uninstall:
  ./uninstall.sh

===================================
EOF
