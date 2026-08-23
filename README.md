# Snap Memory Rescue

Snap Memory Rescue turns a Snapchat Memories export into an ordinary archive of photos and videos that can be imported into Apple Photos, Google Photos, or another photo library.

Everything runs locally on your computer. Drop in the original Snapchat ZIP and every numbered ZIP part, wait for the restore, then download one clean ZIP.

## What it restores

- Original capture dates in EXIF, XMP, and QuickTime metadata
- GPS coordinates when they are present in Snapchat's export
- Snapchat overlays baked into photos and videos
- Chronological, readable filenames
- A `rescue-report.json` containing counts, warnings, and any failures

The app supports Snapchat's current split exports, where media is included under `memories/`. It also supports older single-ZIP HTML exports while their Snapchat download links remain valid.

## Before you start

Request and download your data from the [Snapchat Accounts Portal](https://accounts.snapchat.com/). Include **Memories and Other Media**, and keep every ZIP part together.

You will need:

- Python 3.10 or newer
- [ExifTool](https://exiftool.org/) to embed capture dates and GPS data
- [FFmpeg](https://ffmpeg.org/download.html) to bake overlays into videos
- Free disk space of roughly three times the size of the Snapchat export while processing

`My Eyes Only` content is not normally included in a Snapchat export. Move anything you want to preserve out of My Eyes Only before requesting the export.

## Run on macOS

Install the system tools once:

```bash
brew install exiftool ffmpeg
```

Then download this repository and double-click `start.command`, or run:

```bash
git clone https://github.com/Fouadktb/snap-memory-rescue.git
cd snap-memory-rescue
./start.command
```

The first launch creates a private Python environment and installs the app. Your browser opens at <http://127.0.0.1:8000>.

## Run on Windows or Linux

Install ExifTool and FFmpeg using your system's package manager, then create a virtual environment:

```bash
python3 -m venv .venv
```

Activate it:

```bash
# Windows PowerShell
.venv\Scripts\Activate.ps1

# Linux/macOS
source .venv/bin/activate
```

Install and start the app:

```bash
python -m pip install -e .
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000> if it does not open automatically.

## Restore and import

1. Drop the original Snapchat ZIP and **all** numbered ZIP parts into the page at the same time.
2. Leave the page open while it processes the archive.
3. Download `snap-memory-rescue.zip`.
4. Unzip it.
5. In Apple Photos, choose **File → Import**, or drag the restored photos and videos into the Photos window.
6. Review `rescue-report.json` before deleting anything from Snapchat.

Apple Photos reads the embedded date and location metadata during import. Do not import the ZIP itself; unzip it first.

## Privacy and cleanup

- The web server binds to `127.0.0.1`, so it is accessible only from your computer.
- Current exports are processed fully offline. No archive, account credential, analytics event, or telemetry is sent anywhere.
- Legacy HTML exports may download their media directly from the Snapchat links contained in the export.
- Temporary working files are removed after the finished ZIP is downloaded. Files left by an interrupted run are removed the next time the app starts.
- The app does not delete anything from Snapchat.

## Troubleshooting

**“No memories JSON was found”**

Select the original ZIP along with every numbered part. The JSON metadata is usually in the first archive while media is distributed across the others.

**Some items have no location**

Snapchat does not include GPS for every Memory. The report will distinguish missing source metadata from processing failures.

**The app reports missing ExifTool or FFmpeg**

Install both tools, close the terminal running the app, and start it again.

**The browser closes or the computer sleeps**

Start the app again and rerun the export. Source ZIPs are never modified.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
```

Bug reports and tested export-format samples with all personal data removed are welcome. Never attach a real Snapchat export to a public issue.

## Disclaimer

Snap Memory Rescue is an independent open-source project and is not affiliated with, endorsed by, or sponsored by Snap Inc. Snapchat is a trademark of Snap Inc.

Licensed under the [MIT License](LICENSE).
