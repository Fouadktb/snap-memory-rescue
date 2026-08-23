from datetime import datetime, timezone
import io
import json
from pathlib import Path
import zipfile

import pytest
from PIL import Image

from app.core import discover_history, parse_memories_html, process_exports, safe_extract


HTML = """<table><tbody><tr><th>Date</th><th>Media Type</th><th>Location</th><th></th></tr>
<tr><td>2019-07-04 14:32:08 UTC</td><td>Video</td><td>Latitude, Longitude: 34.0259, -118.7798</td>
<td><a href="#" onclick="downloadMemories('https://example.com/a?x=1', this, true); return false;">Download</a></td></tr></tbody></table>"""


def test_parses_snapchat_table():
    memory = parse_memories_html(HTML)[0]
    assert memory.captured_at.tzinfo == timezone.utc
    assert memory.latitude == 34.0259
    assert memory.longitude == -118.7798
    assert memory.url == "https://example.com/a?x=1"
    assert memory.use_get is True


def test_finds_nested_history(tmp_path: Path):
    history = tmp_path / "mydata" / "html" / "memories_history.html"
    history.parent.mkdir(parents=True)
    history.write_text(HTML)
    assert discover_history(tmp_path) == history


def test_rejects_zip_slip(tmp_path: Path):
    archive_path = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../escape.txt", "bad")
    with zipfile.ZipFile(archive_path) as archive, pytest.raises(ValueError):
        safe_extract(archive, tmp_path / "out")


def test_restores_a_current_split_export(tmp_path: Path, monkeypatch):
    first = tmp_path / "export.zip"
    second = tmp_path / "export-1.zip"
    captured = datetime(2024, 4, 19, 12, 34, 56, tzinfo=timezone.utc)
    metadata = {
        "Saved Media": [{
            "Date": "2024-04-19 12:34:56 UTC",
            "Media Type": "Image",
            "Location": "Latitude, Longitude: 52.5200, 13.4050",
        }]
    }
    with zipfile.ZipFile(first, "w") as archive:
        archive.writestr("json/memories_history.json", json.dumps(metadata))

    image_bytes = io.BytesIO()
    Image.new("RGB", (4, 4), "yellow").save(image_bytes, format="JPEG")
    entry = zipfile.ZipInfo("memories/2024-04-19_example-main.jpg", captured.timetuple()[:6])
    with zipfile.ZipFile(second, "w") as archive:
        archive.writestr(entry, image_bytes.getvalue())

    applied = []
    monkeypatch.setattr("app.core.apply_metadata", lambda path, memory: applied.append((path, memory)) or None)
    reports = []
    progress = []
    output = tmp_path / "restored"

    summary = process_exports([first, second], output, reports.append, lambda *values: progress.append(values))

    files = list(output.glob("*.jpg"))
    assert len(files) == 1
    assert files[0].name == "2024-04-19_12-34-56_example.jpg"
    assert summary["restored"] == 1
    assert summary["failed"] == 0
    assert reports == [summary]
    assert progress == [(1, 1, 1, 0)]
    assert applied[0][1].latitude == 52.52
    assert applied[0][1].longitude == 13.405
