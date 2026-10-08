#!/bin/bash
set -euo pipefail

# Build in a temporary copy so packaging never cleans the development checkout.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

if ! command -v dpkg-buildpackage >/dev/null; then
    echo "Install the build dependencies listed in PACKAGING.md."
    exit 1
fi
BUILD_FLAGS=(-us -uc -b)
if [[ "$#" -eq 1 && "$1" == "--no-check-builddeps" ]]; then
    # For isolated builders that provide build dependencies outside dpkg's database.
    BUILD_FLAGS+=(-d)
elif [[ "$#" -eq 0 ]]; then
    dpkg-checkbuilddeps
else
    echo "Usage: $0 [--no-check-builddeps]"
    exit 2
fi

PACKAGE_VERSION="$(dpkg-parsechangelog -S Version)"
BUILD_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/cowriter-build.XXXXXXXX")"
trap 'rm -rf -- "${BUILD_ROOT}"' EXIT
SOURCE_DIR="${BUILD_ROOT}/cowriter-${PACKAGE_VERSION%-*}"
mkdir -p "${SOURCE_DIR}"

tar --exclude='__pycache__' --exclude='*.pyc' --exclude='*.egg-info' \
    --exclude='debian/cowriter' --exclude='debian/.debhelper' \
    --exclude='debian/files' --exclude='debian/debhelper-build-stamp' \
    --exclude='debian/*.substvars' --exclude='debian/*.debhelper' \
    -cf - src/cowriter tests debian data pyproject.toml README.md PACKAGING.md CHANGELOG.md LICENSE \
    | tar -xf - -C "${SOURCE_DIR}"

echo "Building Co-Writer ${PACKAGE_VERSION}..."
(
    cd "${SOURCE_DIR}"
    dpkg-buildpackage "${BUILD_FLAGS[@]}"
)

mkdir -p "${SCRIPT_DIR}/dist"
cp "${BUILD_ROOT}/cowriter_${PACKAGE_VERSION}_all.deb" "${SCRIPT_DIR}/dist/"
cp "${BUILD_ROOT}"/*.buildinfo "${BUILD_ROOT}"/*.changes "${SCRIPT_DIR}/dist/"
(
    cd "${SCRIPT_DIR}/dist"
    sha256sum "cowriter_${PACKAGE_VERSION}_all.deb" > SHA256SUMS
)
echo "Installer: ${SCRIPT_DIR}/dist/cowriter_${PACKAGE_VERSION}_all.deb"
echo "Install with: sudo apt install ./dist/cowriter_${PACKAGE_VERSION}_all.deb"
