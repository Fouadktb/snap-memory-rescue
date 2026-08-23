from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import uuid
import zipfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from .core import process_exports
from .tools import resolve_exiftool, resolve_ffmpeg

ROOT = Path(__file__).resolve().parent
WORK_ROOT = Path(tempfile.gettempdir()) / "snap-memory-rescue"
WORK_ROOT.mkdir(exist_ok=True)


def process_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


# Keep simultaneous local instances isolated, while removing files left by
# interrupted sessions whose process no longer exists.
for stale_session in WORK_ROOT.iterdir():
    if not stale_session.is_dir():
        continue
    try:
        active = process_is_running(int(stale_session.name))
    except ValueError:
        active = False
    if not active:
        shutil.rmtree(stale_session, ignore_errors=True)

WORK = WORK_ROOT / str(os.getpid())
WORK.mkdir(exist_ok=True)
JOBS: dict[str, dict] = {}
app = FastAPI(title="Memory Rescue", docs_url=None, redoc_url=None)


def missing_tools() -> list[str]:
    return [name for name, path in (("ExifTool", resolve_exiftool()), ("FFmpeg", resolve_ffmpeg())) if not path]


def public_job(job: dict) -> dict:
    return {key: value for key, value in job.items() if key not in {"archive", "folder"}}


def cleanup_job(job_id: str) -> None:
    job = JOBS.pop(job_id, None)
    if job and job.get("folder"):
        shutil.rmtree(job["folder"], ignore_errors=True)


def run_job(job_id: str, sources: list[Path]) -> None:
    job = JOBS[job_id]
    try:
        folder = sources[0].parent
        output = folder / "restored"
        def progress(current, total, restored, failed):
            job.update(status="processing", current=current, total=total, restored=restored, failed=failed)
        def report(summary):
            (output / "rescue-report.json").write_text(json.dumps(summary, indent=2))
        summary = process_exports(sources, output, report, progress)
        archive = folder / "memory-rescue-archive.zip"
        # Photos and videos are already compressed, so recompressing only slows
        # down large exports without meaningfully shrinking the result.
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED, allowZip64=True) as bundle:
            for path in output.rglob("*"):
                if path.is_file():
                    bundle.write(path, path.relative_to(output))
        job.update(status="complete", summary=summary, archive=str(archive))
    except Exception as exc:
        job.update(status="error", error=str(exc))
        shutil.rmtree(job["folder"], ignore_errors=True)
        job["folder"] = None


@app.post("/api/jobs", status_code=202)
async def create_job(exports: list[UploadFile] = File(...)):
    missing = missing_tools()
    if missing:
        raise HTTPException(
            503,
            f"Could not find {', '.join(missing)}. Start the app with the included launcher to set up its tools.",
        )
    if not exports or any(not item.filename or not item.filename.lower().endswith(".zip") for item in exports):
        raise HTTPException(400, "Choose all ZIP files Snapchat sent you.")
    job_id = uuid.uuid4().hex
    folder = WORK / job_id
    folder.mkdir()
    sources = []
    for index, upload in enumerate(exports):
        source = folder / f"part-{index:03d}.zip"
        with source.open("wb") as destination:
            shutil.copyfileobj(upload.file, destination, length=1024 * 1024)
        if not zipfile.is_zipfile(source):
            shutil.rmtree(folder)
            raise HTTPException(400, f"{upload.filename} is not a valid ZIP archive.")
        sources.append(source)
    JOBS[job_id] = {
        "id": job_id, "status": "queued", "current": 0, "total": 0,
        "restored": 0, "failed": 0, "folder": str(folder),
    }
    threading.Thread(target=run_job, args=(job_id, sources), daemon=True).start()
    return public_job(JOBS[job_id])


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404, "Rescue job not found.")
    return public_job(JOBS[job_id])


@app.get("/api/jobs/{job_id}/download")
def download_job(job_id: str):
    job = JOBS.get(job_id)
    if not job or job.get("status") != "complete":
        raise HTTPException(404, "The archive is not ready.")
    return FileResponse(
        job["archive"],
        filename="snap-memory-rescue.zip",
        media_type="application/zip",
        background=BackgroundTask(cleanup_job, job_id),
    )


app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")
