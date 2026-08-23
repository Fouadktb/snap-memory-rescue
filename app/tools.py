from __future__ import annotations

import hashlib
import os
import shutil
import struct
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from imageio_ffmpeg import get_ffmpeg_exe

EXIFTOOL_VERSION = "13.59"
EXIFTOOL_WINDOWS = {
    64: {
        "url": f"https://sourceforge.net/projects/exiftool/files/exiftool-{EXIFTOOL_VERSION}_64.zip/download",
        "sha256": "44b512b25af500724ba579d0a53c8fc5851628b692dd5e5d94ae4a15c2cba9ec",
    },
    32: {
        "url": f"https://sourceforge.net/projects/exiftool/files/exiftool-{EXIFTOOL_VERSION}_32.zip/download",
        "sha256": "fe9a55d28b05c1b0e18877b4881f40d83db222f90018963473cff798e8bf05af",
    },
}


def is_windows() -> bool:
    return os.name == "nt"


def tools_home() -> Path:
    override = os.environ.get("SNAP_MEMORY_RESCUE_TOOLS")
    if override:
        return Path(override).expanduser().resolve()
    if is_windows():
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "SnapMemoryRescue" / "tools"
    return Path.home() / ".cache" / "snap-memory-rescue" / "tools"


def _configured_executable(environment_name: str) -> str | None:
    configured = os.environ.get(environment_name)
    if configured and Path(configured).is_file():
        return str(Path(configured).resolve())
    return None


def bundled_exiftool_path() -> Path:
    bits = struct.calcsize("P") * 8
    folder = tools_home() / f"exiftool-{EXIFTOOL_VERSION}_{bits}"
    return folder / "exiftool.exe"


def resolve_exiftool() -> str | None:
    configured = _configured_executable("SNAP_MEMORY_RESCUE_EXIFTOOL")
    if configured:
        return configured
    system = shutil.which("exiftool") or shutil.which("exiftool.exe")
    if system:
        return system
    if is_windows() and bundled_exiftool_path().is_file():
        return str(bundled_exiftool_path())
    return None


def resolve_ffmpeg() -> str | None:
    configured = _configured_executable("SNAP_MEMORY_RESCUE_FFMPEG")
    if configured:
        return configured
    system = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if system:
        return system
    try:
        bundled = Path(get_ffmpeg_exe())
    except RuntimeError:
        return None
    return str(bundled) if bundled.is_file() else None


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "SnapMemoryRescue/1.1"})
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as target:
        shutil.copyfileobj(response, target, length=1024 * 1024)


def _safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    root = destination.resolve()
    for item in archive.infolist():
        target = (destination / item.filename).resolve()
        if target != root and root not in target.parents:
            raise RuntimeError(f"Unsafe file in ExifTool archive: {item.filename}")
    archive.extractall(destination)


def install_windows_exiftool() -> str:
    existing = resolve_exiftool()
    if existing:
        return existing
    if not is_windows():
        raise RuntimeError("Automatic ExifTool setup is currently available on Windows only.")

    bits = struct.calcsize("P") * 8
    distribution = EXIFTOOL_WINDOWS[bits]
    destination = bundled_exiftool_path().parent
    destination.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="snap-memory-rescue-tools-") as temp_name:
        temp = Path(temp_name)
        download = temp / "exiftool.zip"
        _download(distribution["url"], download)
        digest = hashlib.sha256(download.read_bytes()).hexdigest()
        if digest != distribution["sha256"]:
            raise RuntimeError("ExifTool download failed its security check. Please try again later.")

        extracted = temp / "extracted"
        with zipfile.ZipFile(download) as archive:
            _safe_extract(archive, extracted)
        source = extracted / destination.name
        if not source.is_dir():
            raise RuntimeError("The downloaded ExifTool package had an unexpected layout.")
        shutil.copytree(source, destination, dirs_exist_ok=True)

    original = destination / "exiftool(-k).exe"
    executable = destination / "exiftool.exe"
    if original.exists():
        original.replace(executable)
    if not executable.is_file():
        raise RuntimeError("ExifTool was downloaded but its executable could not be found.")

    result = subprocess.run([str(executable), "-ver"], capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "The bundled ExifTool could not start.")
    return str(executable)


def prepare_runtime_tools() -> dict[str, str]:
    exiftool = resolve_exiftool()
    if not exiftool and is_windows():
        exiftool = install_windows_exiftool()
    ffmpeg = resolve_ffmpeg()
    missing = [name for name, path in (("ExifTool", exiftool), ("FFmpeg", ffmpeg)) if not path]
    if missing:
        raise RuntimeError(f"Missing required tool: {', '.join(missing)}. See the README for setup instructions.")
    return {"exiftool": exiftool, "ffmpeg": ffmpeg}
