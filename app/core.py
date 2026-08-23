from __future__ import annotations

import html
import json
import mimetypes
import os
import re
import shutil
import subprocess
import time
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx
from bs4 import BeautifulSoup
from PIL import Image

from .tools import resolve_exiftool, resolve_ffmpeg

MEDIA_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".webp", ".gif", ".mp4", ".mov", ".m4v"}
DOWNLOAD_RE = re.compile(r"downloadMemories\(\s*['\"](.*?)['\"]\s*,\s*this\s*,\s*(true|false)", re.I)
COORD_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)")


@dataclass
class Memory:
    captured_at: datetime
    media_type: str
    latitude: float | None
    longitude: float | None
    url: str | None
    use_get: bool = True


def safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    root = destination.resolve()
    for item in archive.infolist():
        target = (destination / item.filename).resolve()
        if target != root and root not in target.parents:
            raise ValueError(f"Unsafe ZIP entry: {item.filename}")
    archive.extractall(destination)


def parse_timestamp(value: str) -> datetime:
    cleaned = value.strip().replace(" UTC", "+00:00")
    parsed = datetime.fromisoformat(cleaned)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_memories_html(source: str) -> list[Memory]:
    soup = BeautifulSoup(source, "html.parser")
    memories: list[Memory] = []
    for row in soup.select("table tr"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue
        try:
            captured_at = parse_timestamp(cells[0].get_text(" ", strip=True))
        except (ValueError, TypeError):
            continue
        location = cells[2].get_text(" ", strip=True)
        match = COORD_RE.search(location)
        link = row.find("a")
        onclick = html.unescape(link.get("onclick", "")) if link else ""
        download = DOWNLOAD_RE.search(onclick)
        direct_href = link.get("href") if link and link.get("href") not in (None, "#") else None
        memories.append(Memory(
            captured_at=captured_at,
            media_type=cells[1].get_text(" ", strip=True).lower(),
            latitude=float(match.group(1)) if match else None,
            longitude=float(match.group(2)) if match else None,
            url=download.group(1) if download else direct_href,
            use_get=download is None or download.group(2).lower() == "true",
        ))
    return memories


def discover_history(root: Path) -> Path:
    candidates = list(root.rglob("memories_history.html"))
    if not candidates:
        candidates = [p for p in root.rglob("*.html") if "memories" in p.name.lower()]
    if not candidates:
        raise ValueError("No memories_history.html was found in this export.")
    return candidates[0]


def extension_from_response(response: httpx.Response, fallback_type: str) -> str:
    disposition = response.headers.get("content-disposition", "")
    named = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", disposition, re.I)
    if named:
        suffix = Path(unquote(named.group(1))).suffix.lower()
        if suffix:
            return suffix
    content_type = response.headers.get("content-type", "").split(";", 1)[0]
    if content_type == "application/zip":
        return ".zip"
    return mimetypes.guess_extension(content_type) or (".mp4" if "video" in fallback_type else ".jpg")


def metadata_args(memory: Memory) -> list[str]:
    stamp = memory.captured_at.strftime("%Y:%m:%d %H:%M:%S")
    iso = memory.captured_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    args = [
        f"-EXIF:DateTimeOriginal={stamp}", f"-EXIF:CreateDate={stamp}",
        f"-XMP:DateTimeOriginal={iso}", f"-XMP:CreateDate={iso}",
        f"-QuickTime:CreateDate={stamp}", f"-QuickTime:MediaCreateDate={stamp}",
        f"-QuickTime:TrackCreateDate={stamp}", "-overwrite_original",
    ]
    if memory.latitude is not None and memory.longitude is not None:
        args += [
            f"-GPSLatitude={abs(memory.latitude)}", f"-GPSLatitudeRef={'N' if memory.latitude >= 0 else 'S'}",
            f"-GPSLongitude={abs(memory.longitude)}", f"-GPSLongitudeRef={'E' if memory.longitude >= 0 else 'W'}",
            f"-XMP:GPSLatitude={memory.latitude}", f"-XMP:GPSLongitude={memory.longitude}",
        ]
    return args


def apply_metadata(path: Path, memory: Memory) -> str | None:
    exiftool = resolve_exiftool()
    warning = None
    if exiftool:
        result = subprocess.run([exiftool, *metadata_args(memory), str(path)], capture_output=True, text=True)
        if result.returncode:
            warning = result.stderr.strip() or "ExifTool could not write this file."
    else:
        warning = "ExifTool is not installed; file dates were restored but embedded metadata was skipped."
    timestamp = memory.captured_at.timestamp()
    os.utime(path, (timestamp, timestamp))
    return warning


def download_memory(client: httpx.Client, memory: Memory, target: Path) -> tuple[Path, httpx.Response]:
    if not memory.url:
        raise ValueError("This row has no download link.")
    headers = {"User-Agent": "Mozilla/5.0 MemoryRescue/1.0"}
    if memory.use_get:
        headers["X-Snap-Route-Tag"] = "mem-dmd"
        response = client.get(memory.url, headers=headers)
    else:
        parts = memory.url.split("?", 1)
        response = client.post(parts[0], content=parts[1] if len(parts) > 1 else "", headers={**headers, "Content-Type": "application/x-www-form-urlencoded"})
    response.raise_for_status()
    extension = extension_from_response(response, memory.media_type)
    output = target.with_suffix(extension)
    output.write_bytes(response.content)
    return output, response


def process_export(export_zip: Path, output_dir: Path, report, progress) -> dict:
    extracted = output_dir.parent / "source"
    extracted.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(export_zip) as archive:
        safe_extract(archive, extracted)
    history = discover_history(extracted)
    memories = parse_memories_html(history.read_text(encoding="utf-8", errors="replace"))
    if not memories:
        raise ValueError("The memories file was found, but it did not contain any recognizable memories.")
    failures, warnings, written = [], [], 0
    with httpx.Client(follow_redirects=True, timeout=90) as client:
        for index, memory in enumerate(memories, 1):
            base = output_dir / f"{memory.captured_at:%Y-%m-%d_%H-%M-%S}_{index:05d}"
            try:
                downloaded, response = download_memory(client, memory, base)
                files = []
                if downloaded.suffix.lower() == ".zip":
                    nested = output_dir.parent / f"nested-{index}"
                    nested.mkdir()
                    with zipfile.ZipFile(downloaded) as archive:
                        safe_extract(archive, nested)
                    downloaded.unlink()
                    media_files = (p for p in nested.rglob("*") if p.is_file() and p.suffix.lower() in MEDIA_EXTENSIONS)
                    for part, source in enumerate(media_files, 1):
                        destination = base.with_name(f"{base.name}_{part:02d}").with_suffix(source.suffix.lower())
                        shutil.move(source, destination)
                        files.append(destination)
                else:
                    files.append(downloaded)
                for file in files:
                    warning = apply_metadata(file, memory)
                    if warning:
                        warnings.append({"file": file.name, "message": warning})
                    written += 1
            except Exception as exc:
                failures.append({"index": index, "date": memory.captured_at.isoformat(), "message": str(exc)})
            progress(index, len(memories), written, len(failures))
    summary = {"total": len(memories), "restored": written, "failed": len(failures), "failures": failures, "warnings": warnings}
    report(summary)
    return summary


def parse_json_metadata(source: bytes) -> list[Memory]:
    payload = json.loads(source)
    rows = payload.get("Saved Media", []) if isinstance(payload, dict) else payload
    memories = []
    for row in rows:
        match = COORD_RE.search(row.get("Location", ""))
        latitude = float(match.group(1)) if match else None
        longitude = float(match.group(2)) if match else None
        if latitude == 0 and longitude == 0:
            latitude = longitude = None
        memories.append(Memory(
            captured_at=parse_timestamp(row["Date"]),
            media_type=row.get("Media Type", "").lower(),
            latitude=latitude,
            longitude=longitude,
            url=None,
        ))
    return memories


def rounded_zip_key(captured_at: datetime, extension: str) -> tuple[datetime, str]:
    rounded = captured_at.replace(second=captured_at.second // 2 * 2, microsecond=0)
    return rounded, extension.lower()


def memory_key(memory: Memory) -> tuple[datetime, str]:
    extension = ".mp4" if "video" in memory.media_type else ".jpg"
    return rounded_zip_key(memory.captured_at, extension)


def zip_entry_time(info: zipfile.ZipInfo) -> datetime:
    # Snapchat writes UTC into the DOS field; ZIP precision rounds odd seconds down.
    return datetime(*info.date_time, tzinfo=timezone.utc)


def extract_entry(archive_path: Path, entry: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive, archive.open(entry) as source, destination.open("wb") as target:
        shutil.copyfileobj(source, target, length=1024 * 1024)


def composite_image(main: Path, overlay: Path, output: Path) -> None:
    with Image.open(main) as base_image, Image.open(overlay) as overlay_image:
        base = base_image.convert("RGBA")
        layer = overlay_image.convert("RGBA")
        if layer.size != base.size:
            layer = layer.resize(base.size, Image.Resampling.LANCZOS)
        Image.alpha_composite(base, layer).convert("RGB").save(output, quality=96, subsampling=0)


def composite_video(main: Path, overlay: Path, output: Path) -> None:
    ffmpeg = resolve_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required to bake overlays into videos.")
    result = subprocess.run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(main), "-i", str(overlay),
        "-filter_complex", "[1:v][0:v]scale2ref[overlay][base];[base][overlay]overlay=0:0:format=auto[outv]",
        "-map", "[outv]", "-map", "0:a?", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "copy",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output),
    ], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "FFmpeg could not composite this video overlay.")


def process_split_exports(archives: list[Path], output_dir: Path, report, progress) -> dict:
    if not archives:
        raise ValueError("Choose every ZIP part from your Snapchat export.")
    entry_index: dict[str, Path] = {}
    metadata_source: bytes | None = None
    duplicate_entries = 0
    for archive_path in archives:
        with zipfile.ZipFile(archive_path) as archive:
            if "json/memories_history.json" in archive.namelist():
                metadata_source = archive.read("json/memories_history.json")
            for name in archive.namelist():
                if not name.startswith("memories/") or name.endswith("/"):
                    continue
                if name in entry_index:
                    duplicate_entries += 1
                else:
                    entry_index[name] = archive_path
    if metadata_source is None:
        raise ValueError("No memories JSON was found. Include the first ZIP and every numbered part.")

    memories = parse_json_metadata(metadata_source)
    metadata: dict[tuple[datetime, str], list[Memory]] = {}
    for memory in memories:
        metadata.setdefault(memory_key(memory), []).append(memory)

    main_entries = sorted(name for name in entry_index if "-main." in name)
    output_dir.mkdir(parents=True, exist_ok=True)
    failures, warnings, written, overlays_baked = [], [], 0, 0
    matched_metadata_ids: set[int] = set()
    with tempfile.TemporaryDirectory(prefix="memory-rescue-") as temp_name:
        temp = Path(temp_name)
        for index, entry in enumerate(main_entries, 1):
            extension = Path(entry).suffix.lower()
            archive_path = entry_index[entry]
            with zipfile.ZipFile(archive_path) as archive:
                captured_at = zip_entry_time(archive.getinfo(entry))
            bucket = metadata.get(rounded_zip_key(captured_at, extension), [])
            if bucket:
                memory = bucket.pop()
                matched_metadata_ids.add(id(memory))
            else:
                memory = Memory(captured_at, "video" if extension == ".mp4" else "image", None, None, None)
            identifier = Path(entry).stem.rsplit("-main", 1)[0].split("_", 1)[-1]
            destination = output_dir / f"{memory.captured_at:%Y-%m-%d_%H-%M-%S}_{identifier}{extension}"
            main_temp = temp / f"main{extension}"
            try:
                extract_entry(archive_path, entry, main_temp)
                overlay_entry = str(Path(entry).with_name(Path(entry).stem.rsplit("-main", 1)[0] + "-overlay.png"))
                if overlay_entry in entry_index:
                    overlay_temp = temp / "overlay.png"
                    extract_entry(entry_index[overlay_entry], overlay_entry, overlay_temp)
                    if extension == ".mp4":
                        composite_video(main_temp, overlay_temp, destination)
                    else:
                        composite_image(main_temp, overlay_temp, destination)
                    overlays_baked += 1
                    overlay_temp.unlink(missing_ok=True)
                else:
                    shutil.move(main_temp, destination)
                warning = apply_metadata(destination, memory)
                if warning:
                    warnings.append({"file": destination.name, "message": warning})
                written += 1
            except Exception as exc:
                failures.append({"file": entry, "date": memory.captured_at.isoformat(), "message": str(exc)})
            finally:
                main_temp.unlink(missing_ok=True)
            progress(index, len(main_entries), written, len(failures))

    summary = {
        "total": len(main_entries), "restored": written, "failed": len(failures),
        "overlays_baked": overlays_baked, "duplicate_entries_ignored": duplicate_entries,
        "metadata_rows_without_media": len(memories) - len(matched_metadata_ids),
        "failures": failures, "warnings": warnings,
    }
    report(summary)
    return summary


def process_exports(archives: list[Path], output_dir: Path, report, progress) -> dict:
    """Process current split exports or a legacy single-file HTML export."""
    contains_json = False
    for archive_path in archives:
        with zipfile.ZipFile(archive_path) as archive:
            if "json/memories_history.json" in archive.namelist():
                contains_json = True
                break
    if contains_json:
        return process_split_exports(archives, output_dir, report, progress)
    if len(archives) == 1:
        return process_export(archives[0], output_dir, report, progress)
    raise ValueError("No memories JSON was found. Include the first ZIP and every numbered part.")
