import hashlib
import io
import shutil
import struct
import subprocess
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import tools


def test_resolves_configured_exiftool(tmp_path: Path, monkeypatch):
    executable = tmp_path / "custom-exiftool"
    executable.write_bytes(b"tool")
    monkeypatch.setenv("SNAP_MEMORY_RESCUE_EXIFTOOL", str(executable))

    assert tools.resolve_exiftool() == str(executable)


def test_resolves_packaged_ffmpeg(tmp_path: Path, monkeypatch):
    executable = tmp_path / "ffmpeg"
    executable.write_bytes(b"tool")
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    monkeypatch.setattr(tools, "get_ffmpeg_exe", lambda: str(executable))

    assert tools.resolve_ffmpeg() == str(executable)


def test_installs_verified_windows_exiftool(tmp_path: Path, monkeypatch):
    bits = struct.calcsize("P") * 8
    folder_name = f"exiftool-{tools.EXIFTOOL_VERSION}_{bits}"
    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w") as archive:
        archive.writestr(f"{folder_name}/exiftool(-k).exe", b"executable")
        archive.writestr(f"{folder_name}/exiftool_files/LICENSE", b"license")
    payload = archive_bytes.getvalue()

    monkeypatch.delenv("SNAP_MEMORY_RESCUE_EXIFTOOL", raising=False)
    monkeypatch.setattr(tools, "is_windows", lambda: True)
    monkeypatch.setattr(tools, "tools_home", lambda: tmp_path / "tools")
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    monkeypatch.setitem(tools.EXIFTOOL_WINDOWS[bits], "sha256", hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(tools, "_download", lambda _url, destination: destination.write_bytes(payload))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=tools.EXIFTOOL_VERSION, stderr=""),
    )

    executable = Path(tools.install_windows_exiftool())

    assert executable.name == "exiftool.exe"
    assert executable.read_bytes() == b"executable"
    assert (executable.parent / "exiftool_files" / "LICENSE").is_file()


def test_rejects_unsafe_tool_archive(tmp_path: Path):
    source = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("../outside.txt", b"bad")

    with zipfile.ZipFile(source) as archive, pytest.raises(RuntimeError):
        tools._safe_extract(archive, tmp_path / "tools")
