import io
from pathlib import Path
import zipfile

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_missing_tools_are_reported(monkeypatch):
    monkeypatch.setattr("app.main.missing_tools", lambda: ["ExifTool", "FFmpeg"])
    response = client.post("/api/jobs", files=[("exports", ("export.zip", b"x", "application/zip"))])
    assert response.status_code == 503
    assert "Could not find ExifTool, FFmpeg" in response.json()["detail"]


def test_home_page_loads():
    response = client.get("/")
    assert response.status_code == 200
    assert "Drop every Snapchat ZIP here" in response.text


def test_rejects_non_zip_upload(monkeypatch):
    monkeypatch.setattr("app.main.missing_tools", lambda: [])
    response = client.post("/api/jobs", files=[("exports", ("export.zip", b"not a zip", "application/zip"))])
    assert response.status_code == 400
    assert response.json()["detail"] == "export.zip is not a valid ZIP archive."


def test_accepts_valid_export(monkeypatch):
    monkeypatch.setattr("app.main.missing_tools", lambda: [])
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("html/memories_history.html", "<table></table>")
    monkeypatch.setattr("app.main.run_job", lambda *args: None)
    response = client.post("/api/jobs", files=[("exports", ("snapchat.zip", archive.getvalue(), "application/zip"))])
    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert "folder" not in response.json()


def test_download_removes_temporary_job(tmp_path: Path):
    from app.main import JOBS

    folder = tmp_path / "job"
    folder.mkdir()
    archive = folder / "archive.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("photo.jpg", b"photo")
    JOBS["download-test"] = {
        "id": "download-test", "status": "complete", "archive": str(archive),
        "folder": str(folder),
    }

    response = client.get("/api/jobs/download-test/download")

    assert response.status_code == 200
    assert response.headers["content-disposition"].endswith('filename="snap-memory-rescue.zip"')
    assert not folder.exists()
    assert "download-test" not in JOBS
