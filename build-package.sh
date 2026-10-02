#!/bin/bash
set -e

echo "=== Co-Writer Ubuntu Package Build Script ==="
echo ""

echo "1. Checking build dependencies..."
REQUIRED_PACKAGES="debhelper dh-python python3-all python3-setuptools python3-requests python3-markdown-it python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 python3-pypdf python3-striprtf"
MISSING_PACKAGES=""

for pkg in $REQUIRED_PACKAGES; do
    if ! dpkg -l | grep -q "^ii  $pkg "; then
        MISSING_PACKAGES="$MISSING_PACKAGES $pkg"
    fi
done

if [ -n "$MISSING_PACKAGES" ]; then
    echo "Missing packages:$MISSING_PACKAGES"
    echo "Install with: sudo apt-get install$MISSING_PACKAGES"
    exit 1
fi

echo "All build dependencies installed."
echo ""

echo "2. Cleaning previous builds..."
rm -rf dist/ build/ src/*.egg-info debian/cowriter debian/files debian/.debhelper debian/debhelper-build-stamp 2>/dev/null || true

echo "3. Building Python package..."
python3 -m build --wheel
echo ""

echo "4. Building Debian package..."
dpkg-buildpackage -us -uc -b
echo ""

echo "5. Package built successfully!"
echo ""
echo "Package files:"
ls -lh ../cowriter_*.deb 2>/dev/null || ls -lh *.deb 2>/dev/null || echo "Check parent directory for .deb files"
echo ""
echo "To install:"
echo "  sudo dpkg -i ../cowriter_*.deb"
echo "  sudo apt-get install -f  # Fix any missing dependencies"
echo ""
echo "To run:"
echo "  cowriter-gui  # GUI launcher"
echo "  cowriter      # Console launcher"
