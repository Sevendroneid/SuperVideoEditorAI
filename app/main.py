import json
import logging
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .ai import AIProvider
from .config import get_settings
from .director import DirectorInstructionError, apply_director_instruction
from .jobs import JobStore
from .models import JobRecord, SegmentEvidence, Timeline
from .supabase_store import SupabaseStore

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

WEB_ROOT = Path(__file__).resolve().parent.parent / "web"
supabase = SupabaseStore(settings.supabase_url, settings.supabase_service_role_key, settings.supabase_bucket)
logger = logging.getLogger("supervideoeditorai")
logger.info("Persistent storage enabled: %s", supabase.enabled)


class DirectorRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=500)


def project_path(project_id: str) -> Path:
    if not project_id or len(project_id) > 64 or any(
        c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in project_id
    ):
        raise HTTPException(status_code=400, detail="Invalid project id")
    path = (settings.projects_dir / project_id).resolve()
    projects_root = settings.projects_dir.resolve()
    if path.parent != projects_root:
        raise HTTPException(status_code=404, detail="Project not found")
    if not path.is_dir():
        if supabase.enabled and supabase.get_project(project_id):
            path.mkdir(parents=True, exist_ok=True)
            (path / "jobs").mkdir(exist_ok=True)
        else:
            raise HTTPException(status_code=404, detail="Project not found")
    return path


def load_analysis(project_id: str) -> tuple[Path, dict]:
    path = project_path(project_id)
    analysis_file = path / "analysis.json"
    if analysis_file.is_file():
        try:
            return path, json.loads(analysis_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=500, detail="Analysis state is unreadable") from exc
    if supabase.enabled:
        artifacts = supabase.get_artifacts(project_id, "analysis")
        if artifacts:
            local_copy = path / "analysis.json"
            supabase.download_file(artifacts[0]["storage_path"], local_copy)
            try:
                return path, json.loads(local_copy.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise HTTPException(status_code=500, detail="Persisted analysis state is unreadable") from exc
    raise HTTPException(status_code=409, detail="Analyze the project first")


@app.get("/")
def dashboard():
    return FileResponse(WEB_ROOT / "index.html", media_type="text/html")


@app.get("/app.js")
def dashboard_script():
    return FileResponse(WEB_ROOT / "app.js", media_type="application/javascript")


@app.get("/styles.css")
def dashboard_styles():
    return FileResponse(WEB_ROOT / "styles.css", media_type="text/css")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": settings.app_name, "environment": settings.environment, "persistent_storage": supabase.enabled}


@app.post(f"{settings.api_prefix}/projects")
def create_project() -> dict:
    project_id = uuid.uuid4().hex
    path = settings.projects_dir / project_id
    path.mkdir(parents=True, exist_ok=False)
    (path / "jobs").mkdir()
    if supabase.enabled:
        try:
            supabase.create_project(project_id)
        except Exception as exc:
            shutil.rmtree(path, ignore_errors=True)
            raise HTTPException(status_code=503, detail="Persistent project storage unavailable") from exc
    return {"project_id": project_id}


@app.get(f"{settings.api_prefix}/projects/{{project_id}}/analysis")
def get_analysis(project_id: str) -> dict:
    _, data = load_analysis(project_id)
    return data


@app.post(f"{settings.api_prefix}/projects/{{project_id}}/clips")
async def upload_clip(project_id: str, file: UploadFile = File(...)) -> dict:
    path = project_path(project_id)
    allowed = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower()
    if not filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    if suffix not in allowed:
        raise HTTPException(status_code=415, detail="Unsupported video extension")
    destination = path / f"{uuid.uuid4().hex}{suffix}"
    total = 0
    try:
        with destination.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > settings.max_upload_bytes:
                    raise HTTPException(status_code=413, detail="File exceeds upload limit")
                output.write(chunk)
        if supabase.enabled:
            remote_path = f"{project_id}/{destination.name}"
            content_type = file.content_type or "video/mp4"
            supabase.upload_file(destination, remote_path, content_type)
            supabase.create_clip(project_id, filename, remote_path, total)
    except HTTPException:
        destination.unlink(missing_ok=True)
        raise
    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=503, detail="Unable to persist upload") from exc
    finally:
        await file.close()
    return {"filename": filename, "stored_as": destination.name, "bytes": total, "persistent": supabase.enabled}


@app.post(f"{settings.api_prefix}/projects/{{project_id}}/analyze", status_code=202)
def queue_analysis(project_id: str) -> JobRecord:
    from .worker import analyze_project

    path = project_path(project_id)
    has_local_clips = any(path.glob("*.[mM][pP]4")) or any(path.glob("*.mov")) or any(path.glob("*.mkv")) or any(path.glob("*.webm")) or any(path.glob("*.m4v")) or any(path.glob("*.avi"))
    if not has_local_clips and (not supabase.enabled or not supabase.get_project_clips(project_id)):
        raise HTTPException(status_code=409, detail="Upload at least one video before analysis")
    job_id = str(uuid.uuid4())
    record = JobStore(path / "jobs").create(job_id)
    if supabase.enabled:
        try:
            supabase.create_job(project_id, job_id, "analysis")
        except Exception as exc:
            JobStore(path / "jobs").update(job_id, status="failed", progress=100, message="Unable to persist analysis job", error=str(exc))
            raise HTTPException(status_code=503, detail="Persistent job storage unavailable") from exc
    try:
        analyze_project.delay(job_id, project_id)
    except Exception as exc:
        JobStore(path / "jobs").update(job_id, status="failed", progress=100, message="Unable to queue analysis", error=str(exc))
        if supabase.enabled:
            supabase.update_job(job_id, status="failed", progress=100, message="Unable to queue analysis", error=str(exc))
        raise HTTPException(status_code=503, detail="Background worker unavailable") from exc
    return record


@app.get(f"{settings.api_prefix}/jobs/{{job_id}}")
def get_job(job_id: str):
    if not job_id or len(job_id) > 64 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in job_id):
        raise HTTPException(status_code=400, detail="Invalid job id")
    if supabase.enabled:
        record = supabase.get_job(job_id)
        if record:
            return record
    for project in settings.projects_dir.iterdir():
        if project.is_dir():
            record = JobStore(project / "jobs").get(job_id)
            if record:
                return record
    raise HTTPException(status_code=404, detail="Job not found")


@app.post(f"{settings.api_prefix}/projects/{{project_id}}/render", status_code=202)
def queue_render(project_id: str) -> JobRecord:
    from .worker import render_project

    path, analysis = load_analysis(project_id)
    if not analysis.get("timeline", {}).get("items"):
        raise HTTPException(status_code=409, detail="Timeline contains no renderable clips")
    job_id = str(uuid.uuid4())
    record = JobStore(path / "jobs").create(job_id)
    if supabase.enabled:
        try:
            supabase.create_job(project_id, job_id, "render")
        except Exception as exc:
            JobStore(path / "jobs").update(job_id, status="failed", progress=100, message="Unable to persist render job", error=str(exc))
            raise HTTPException(status_code=503, detail="Persistent job storage unavailable") from exc
    try:
        render_project.delay(job_id, project_id)
    except Exception as exc:
        JobStore(path / "jobs").update(job_id, status="failed", progress=100, message="Unable to queue render", error=str(exc))
        if supabase.enabled:
            supabase.update_job(job_id, status="failed", progress=100, message="Unable to queue render", error=str(exc))
        raise HTTPException(status_code=503, detail="Background worker unavailable") from exc
    return record


@app.get(f"{settings.api_prefix}/projects/{{project_id}}/output")
def download_output(project_id: str):
    project_path(project_id)
    path = (settings.outputs_dir / f"{project_id}.mp4").resolve()
    outputs_root = settings.outputs_dir.resolve()
    if path.parent == outputs_root and path.is_file():
        return FileResponse(path, media_type="video/mp4", filename="supervideo-story.mp4")
    if supabase.enabled:
        artifacts = supabase.get_artifacts(project_id, "render")
        if artifacts:
            remote_path = artifacts[0]["storage_path"]
            local_output = settings.outputs_dir / f"{project_id}.mp4"
            supabase.download_file(remote_path, local_output)
            if local_output.is_file():
                return FileResponse(local_output, media_type="video/mp4", filename="supervideo-story.mp4")
    raise HTTPException(status_code=404, detail="Rendered output not found")


@app.post(f"{settings.api_prefix}/projects/{{project_id}}/director")
async def director(project_id: str, request: DirectorRequest):
    project_dir, data = load_analysis(project_id)
    segments = [SegmentEvidence.model_validate(item) for item in data.get("segments", [])]
    current = Timeline.model_validate(data.get("timeline", {"items": [], "total_duration_seconds": 0}))
    try:
        timeline, result = apply_director_instruction(segments, current, request.instruction)
    except DirectorInstructionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if result.get("applied"):
        data["timeline"] = timeline.model_dump()
        data["director_history"] = data.get("director_history", []) + [result]
        analysis_file = project_dir / "analysis.json"
        analysis_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        if supabase.enabled:
            storage_path = f"{project_id}/analysis.json"
            try:
                supabase.upload_file(analysis_file, storage_path, "application/json", upsert=True)
                supabase.create_artifact(project_id, "analysis", storage_path, {"updated_by": "director"})
            except Exception as exc:
                raise HTTPException(status_code=503, detail="Unable to persist director update") from exc
        result["timeline"] = timeline.model_dump()

    provider = AIProvider(settings.ai_provider, settings.ai_base_url, settings.ai_api_key, settings.ai_model)
    ai_context = await provider.generate_story_direction(data.get("clips", []), request.instruction)
    return {**result, "ai": ai_context}
