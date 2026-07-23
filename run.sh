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

# YouTube protects video URLs with a JS "n" challenge that yt-dlp can only
# solve with a Deno runtime (Node does NOT work for this). If the system has
# no Deno, install a private copy into the project so the user never has to
# fetch or set up anything by hand. One-time ~40 MB download.
if ! command -v deno >/dev/null 2>&1 && [ ! -x "./.deno/bin/deno" ]; then
    echo "Installing Deno (one-time) — required for HD downloads..."
    export DENO_INSTALL="$PWD/.deno"
    curl -fsSL https://deno.land/install.sh | DENO_INSTALL="$PWD/.deno" sh -s -- -y
fi
if [ -x "./.deno/bin/deno" ]; then
    export PATH="$PWD/.deno/bin:$PATH"
fi

echo
echo "Starting YT Downloader at http://127.0.0.1:5757"
echo "Press Ctrl+C to stop."
echo
exec "$VENV/bin/python" app.py
