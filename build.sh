#!/usr/bin/env bash
# Poros build script (Linux / macOS)
# Usage: chmod +x build.sh && ./build.sh

set -e

# Only the scratch work directory is cleared. dist also holds previously built
# installers, portable executables and APKs, which must survive a new build.
echo "=== Cleaning work directory ==="
rm -rf build

echo "=== Building ==="
pyinstaller --noconfirm main.spec

echo "=== Build complete ==="
echo "Executable: $(pwd)/dist/Poros"
