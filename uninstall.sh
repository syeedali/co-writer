#!/bin/bash
set -e

echo "==================================="
echo "  Co-Writer — Uninstaller"
echo "==================================="
echo ""

INSTALL_DIR="${HOME}/.local"
DESKTOP_FILE="${INSTALL_DIR}/share/applications/com.github.chukrobertson.cowriter.desktop"
ICON_FILE="${INSTALL_DIR}/share/icons/hicolor/scalable/apps/com.github.chukrobertson.cowriter.svg"
METAINFO_FILE="${INSTALL_DIR}/share/metainfo/com.github.chukrobertson.cowriter.metainfo.xml"
APP_DIR="${INSTALL_DIR}/share/cowriter"

echo "[1/4] Removing Python package..."
pip uninstall cowriter -y --break-system-packages 2>/dev/null || pip uninstall cowriter -y 2>/dev/null || true

echo "[2/4] Removing desktop integration..."
rm -f "${DESKTOP_FILE}"
rm -f "${ICON_FILE}"
rm -f "${INSTALL_DIR}/share/applications/cowriter.desktop"
rm -f "${INSTALL_DIR}/share/icons/hicolor/scalable/apps/cowriter.svg"
rm -f "${METAINFO_FILE}"

echo "[3/4] Updating desktop database..."
update-desktop-database "${INSTALL_DIR}/share/applications" 2>/dev/null || echo "  (skipped)"

echo "[4/4] Cleaning up..."
# The install marker shares a directory with the user's drafts and config.
rm -f "${APP_DIR}/.installed"
rmdir "${APP_DIR}" 2>/dev/null || true

echo ""
echo "Uninstall complete."
echo ""
echo "Your data files are preserved at: ~/.local/share/cowriter/"
echo "To remove them: rm -rf ~/.local/share/cowriter/"
