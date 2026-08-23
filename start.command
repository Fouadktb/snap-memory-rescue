#!/bin/zsh
set -e
cd "${0:A:h}"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -e . --quiet
if ! command -v exiftool >/dev/null 2>&1; then
  echo "Memory Rescue needs ExifTool to preserve dates and GPS inside Apple Photos."
  echo "Install it once with: brew install exiftool"
  read "?Press Return to close."
  exit 1
fi
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "Memory Rescue needs FFmpeg to restore overlays on videos."
  echo "Install it once with: brew install ffmpeg"
  read "?Press Return to close."
  exit 1
fi
open http://127.0.0.1:8000
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
