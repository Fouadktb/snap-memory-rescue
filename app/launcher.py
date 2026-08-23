from __future__ import annotations

import sys
import threading
import webbrowser

import uvicorn

from .tools import prepare_runtime_tools


def main() -> int:
    print("Preparing Snap Memory Rescue…")
    try:
        tools = prepare_runtime_tools()
    except Exception as exc:
        print(f"\nCould not prepare the required tools: {exc}")
        return 1

    print(f"ExifTool: {tools['exiftool']}")
    print(f"FFmpeg:   {tools['ffmpeg']}")
    print("Opening http://127.0.0.1:8000")
    threading.Timer(1.0, webbrowser.open, args=("http://127.0.0.1:8000",)).start()
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000)
    return 0


if __name__ == "__main__":
    sys.exit(main())
