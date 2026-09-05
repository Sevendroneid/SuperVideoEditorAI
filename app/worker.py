import json
import shutil
from pathlib import Path

from celery import Celery

from .analysis import analyze_directory
from .config import Settings, get_settings
from .ffmpeg import FFmpeg
from .jobs import JobStore
from .models import SegmentEvidence
from .segments import extract_segments
from .story import build_baseline_story
from .supabase_store import SupabaseStore

runtime_settings = Settings()
celery_app = Celery("supervideoeditorai", broker=runtime_settings.redis_url, backend=runtime_settings.celery_result_backend)
celery_app.conf.update(
    task_serializer="json", result_serializer="json", accept_content=["json"],
    task_track_started=True, task_time_limit=3600, task_soft_time_limit=3300,
    task_always_eager=runtime_settings.celery_task_always_eager,
)


def _timeline_source(project_dir: Path, raw_path: str) -> Path:
    source = Path(raw_path).resolve()
    root = project_dir.resolve()
    try:
        source.relative_to(root)
    except ValueError as exc:
        raise RuntimeError("Timeline references a file outside the project directory") from exc
    if not source.is_file():
        raise RuntimeError(f"Timeline references missing clip: {source.name}")
    return source


def _stores(settings: Settings, project_id: str):
    project_dir = settings.projects_dir / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "jobs").mkdir(exist_ok=True)
    return project_dir, JobStore(project_dir / "jobs"), SupabaseStore(settings.supabase_url, settings.supabase_service_role_key, settings.supabase_bucket)


def _download_persistent_clips(store: SupabaseStore, project_id: str, project_dir: Path) -> None:
    for clip in store.get_project_clips(project_id):
        filename = Path(clip["storage_path"]).name
        destination = project_dir / filename
        if not destination.is_file():
            store.download_file(clip["storage_path"], destination)


def _persist_job(supabase: SupabaseStore, job_id: str, **changes) -> None:
    if supabase.enabled:
        supabase.update_job(job_id, **changes)


def _persist_analysis(supabase: SupabaseStore, project_id: str, analysis_file: Path) -> None:
    if not supabase.enabled:
        return
    storage_path = f"{project_id}/analysis.json"
    supabase.upload_file(analysis_file, storage_path, "application/json", upsert=True)
    supabase.create_artifact(project_id, "analysis", storage_path, {"format": "json"})


@celery_app.task(bind=True, name="analyze_project")
def analyze_project(self, job_id: str, project_id: str) -> dict:
    settings = get_settings()
    project_dir, local_jobs, supabase = _stores(settings, project_id)
    try:
        local_jobs.update(job_id, status="processing", progress=10, message="Inspecting video files")
        _persist_job(supabase, job_id, status="processing", progress=10, message="Inspecting video files")
        if supabase.enabled:
            _download_persistent_clips(supabase, project_id, project_dir)
        ffmpeg = FFmpeg(settings.ffmpeg_bin, settings.ffprobe_bin)
        clips = analyze_directory(project_dir, ffmpeg)
        if not clips:
            raise RuntimeError("No valid video clips could be analyzed")
        local_jobs.update(job_id, progress=40, message="Scoring smart segments")
        _persist_job(supabase, job_id, progress=40, message="Scoring smart segments")
        segments: list[SegmentEvidence] = []
        for clip in clips:
            segments.extend(SegmentEvidence.model_validate(item) for item in extract_segments(Path(clip.path), clip))
        if not segments:
            raise RuntimeError("No usable video segments were extracted")
        local_jobs.update(job_id, progress=70, message="Building baseline story")
        _persist_job(supabase, job_id, progress=70, message="Building baseline story")
        timeline = build_baseline_story(segments)
        if not timeline.items:
            raise RuntimeError("Unable to build a baseline story from verified segments")
        result = {
            "clips": [item.model_dump() for item in clips],
            "segments": [item.model_dump() for item in segments],
            "timeline": timeline.model_dump(),
        }
        analysis_file = project_dir / "analysis.json"
        analysis_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
        _persist_analysis(supabase, project_id, analysis_file)
        local_jobs.update(job_id, status="completed", progress=100, message="Analysis completed", result=result)
        _persist_job(supabase, job_id, status="completed", progress=100, message="Analysis completed", result=result)
        return result
    except Exception as exc:
        local_jobs.update(job_id, status="failed", progress=100, message="Analysis failed", error=str(exc))
        _persist_job(supabase, job_id, status="failed", progress=100, message="Analysis failed", error=str(exc))
        raise


@celery_app.task(bind=True, name="render_project")
def render_project(self, job_id: str, project_id: str) -> dict:
    settings = get_settings()
    project_dir, local_jobs, supabase = _stores(settings, project_id)
    work_dir = project_dir / "render_segments"
    try:
        local_jobs.update(job_id, status="processing", progress=10, message="Preparing timeline segments")
        _persist_job(supabase, job_id, status="processing", progress=10, message="Preparing timeline segments")
        analysis_file = project_dir / "analysis.json"
        if not analysis_file.is_file() and supabase.enabled:
            artifacts = supabase.get_artifacts(project_id, "analysis")
            if artifacts:
                supabase.download_file(artifacts[0]["storage_path"], analysis_file)
        if not analysis_file.is_file():
            raise RuntimeError("Analysis state not found")
        if supabase.enabled:
            _download_persistent_clips(supabase, project_id, project_dir)
        analysis = json.loads(analysis_file.read_text(encoding="utf-8"))
        items = analysis.get("timeline", {}).get("items", [])
        if not items:
            raise RuntimeError("Timeline contains no clips")
        ffmpeg = FFmpeg(settings.ffmpeg_bin, settings.ffprobe_bin)
        work_dir.mkdir(parents=True, exist_ok=True)
        rendered = []
        for index, item in enumerate(items):
            source = _timeline_source(project_dir, item["clip_path"])
            start = float(item["start_seconds"])
            end = float(item["end_seconds"])
            if start < 0 or end <= start:
                raise RuntimeError("Timeline contains invalid segment boundaries")
            target = work_dir / f"segment_{index:04d}.mp4"
            ffmpeg.extract_segment(source, start, end, target)
            rendered.append(target)
            progress = min(90, 10 + int((index + 1) / len(items) * 80))
            local_jobs.update(job_id, progress=progress, message=f"Rendered segment {index + 1}/{len(items)}")
            _persist_job(supabase, job_id, progress=progress, message=f"Rendered segment {index + 1}/{len(items)}")
        output = settings.outputs_dir / f"{project_id}.mp4"
        ffmpeg.concat(rendered, output)
        result = {"output": str(output), "segments_rendered": len(rendered)}
        if supabase.enabled:
            remote_path = f"{project_id}/output.mp4"
            supabase.upload_file(output, remote_path, "video/mp4", upsert=True)
            supabase.create_artifact(project_id, "render", remote_path, {"segments_rendered": len(rendered)})
            result["storage_path"] = remote_path
        local_jobs.update(job_id, status="completed", progress=100, message="Render completed", result=result)
        _persist_job(supabase, job_id, status="completed", progress=100, message="Render completed", result=result)
        return result
    except Exception as exc:
        local_jobs.update(job_id, status="failed", progress=100, message="Render failed", error=str(exc))
        _persist_job(supabase, job_id, status="failed", progress=100, message="Render failed", error=str(exc))
        raise
    finally:
        if work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)
