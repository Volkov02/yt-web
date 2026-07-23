#!/usr/bin/env bash
# Linux/macOS launcher for yt-web.
set -euo pipefail
cd "$(dirname "$0")"

VENV=".venv"
if [ ! -d "$VENV" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV"
fi

echo "Installing dependencies..."
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r requirements.txt

echo
echo "Starting YT Downloader at http://127.0.0.1:5757"
echo "Press Ctrl+C to stop."
echo
exec "$VENV/bin/python" app.py
