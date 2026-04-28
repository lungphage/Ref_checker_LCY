#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "Building macOS onefile bundle with PyInstaller"
python3 -m pip install --upgrade pip wheel pyinstaller pyinstaller-hooks-contrib setuptools

python3 -m PyInstaller \
  --noconfirm \
  --clean \
  --onefile \
  --windowed \
  --name ReferenceChecker \
  ref_checker_gui.py

echo
echo "Build finished."
echo "Onefile executable: dist/ReferenceChecker"
echo "App bundle: dist/ReferenceChecker.app"
