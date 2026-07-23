#!/usr/bin/env bash
# Build a standalone Linux binary with PyInstaller.
set -euo pipefail
cd "$(dirname "$0")"

VENV=".venv"
if [ ! -d "$VENV" ]; then
    python3 -m venv "$VENV"
fi

echo "=== YT Downloader - Build ==="
echo
echo "[1/2] Installing dependencies..."
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r requirements.txt pyinstaller

echo
echo "[2/2] Building executable..."
# NOTE: on Linux/macOS --add-data uses ':' as separator (Windows uses ';')
"$VENV/bin/python" -m PyInstaller \
    --onefile \
    --name "yt-downloader" \
    --add-data "templates:templates" \
    --collect-all imageio_ffmpeg \
    --hidden-import "yt_dlp" \
    --hidden-import "flask" \
    app.py

echo
echo "Done! Executable: dist/yt-downloader"
