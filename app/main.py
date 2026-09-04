import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .ai import AIProvider
from .config import get_settings
from .jobs import JobStore
from .models import JobRecord
from .worker import analyze_project, render_project

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["*"])


def project_path(project_id: str) -> Path:
    if not project_id or len(project_id) > 64 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in project_id):
        raise HTTPException(status_code=400, detail="Invalid project id")
    path = settings.projects_dir / project_id
    if not path.exists():
        raise HTTPException(status_code=404, detail="Project not found")
    return path


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": settings.app_name, "environment": settings.environment}


@app.post(f"{settings.api_prefix}/projects")
def create_project() -> dict:
    project_id = uuid.uuid4().hex
    path = settings.projects_dir / project_id
    path.mkdir(parents=True, exist_ok=False)
    (path / "jobs").mkdir()
    return {"project_id": project_id}


@app.post(f"{settings.api_prefix}/projects/{{project_id}}/clips")
async def upload_clip(project_id: str, file: UploadFile = File(...)) -> dict:
    path = project_path(project_id)
    allowed = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(status_code=415, detail="Unsupported video extension")
    if not filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    destination = path / f"{uuid.uuid4().hex}{suffix}"
    total = 0
    try:
        with destination.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > settings.max_upload_bytes:
                    raise HTTPException(status_code=413, detail="File exceeds upload limit")
                output.write(chunk)
    except HTTPException:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    return {"filename": filename, "stored_as": destination.name, "bytes": total}


@app.post(f"{settings.api_prefix}/projects/{{project_id}}/analyze", status_code=202)
def queue_analysis(project_id: str) -> JobRecord:
    path = project_path(project_id)
    job_id = uuid.uuid4().hex
    store = JobStore(path / "jobs")
    record = store.create(job_id)
    analyze_project.delay(job_id, project_id)
    return record


@app.get(f"{settings.api_prefix}/jobs/{{job_id}}")
def get_job(job_id: str):
    for project in settings.projects_dir.iterdir():
        if project.is_dir():
            record = JobStore(project / "jobs").get(job_id)
            if record:
                return record
    raise HTTPException(status_code=404, detail="Job not found")


@app.post(f"{settings.api_prefix}/projects/{{project_id}}/render", status_code=202)
def queue_render(project_id: str) -> JobRecord:
    path = project_path(project_id)
    analysis_file = path / "analysis.json"
    if not analysis_file.exists():
        raise HTTPException(status_code=409, detail="Analyze the project before rendering")
    job_id = uuid.uuid4().hex
    record = JobStore(path / "jobs").create(job_id)
    render_project.delay(job_id, project_id)
    return record


@app.get(f"{settings.api_prefix}/projects/{{project_id}}/output")
def download_output(project_id: str):
    path = project_path(project_id) / "output.mp4"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Rendered output not found")
    return FileResponse(path, media_type="video/mp4", filename="supervideo-story.mp4")


@app.post(f"{settings.api_prefix}/projects/{{project_id}}/director")
async def director(project_id: str, instruction: str):
    project_path(project_id)
    analysis_file = settings.projects_dir / project_id / "analysis.json"
    if not analysis_file.exists():
        raise HTTPException(status_code=409, detail="Analyze the project before directing")
    import json
    data = json.loads(analysis_file.read_text(encoding="utf-8"))
    provider = AIProvider(settings.ai_provider, settings.ai_base_url, settings.ai_api_key, settings.ai_model)
    return await provider.generate_story_direction(data.get("clips", []), instruction)
