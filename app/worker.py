import json
from pathlib import Path

from celery import Celery

from .analysis import analyze_directory
from .config import get_settings
from .ffmpeg import FFmpeg
from .jobs import JobStore
from .story import build_baseline_story

settings = get_settings()
celery_app = Celery("supervideoeditorai", broker=settings.redis_url, backend=settings.celery_result_backend)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_time_limit=3600,
    task_soft_time_limit=3300,
)


@celery_app.task(bind=True, name="analyze_project")
def analyze_project(self, job_id: str, project_id: str) -> dict:
    store = JobStore(settings.projects_dir / project_id / "jobs")
    project_dir = settings.projects_dir / project_id
    try:
        store.update(job_id, status="processing", progress=10, message="Analyzing video files")
        ffmpeg = FFmpeg(settings.ffmpeg_bin, settings.ffprobe_bin)
        evidence = analyze_directory(project_dir, ffmpeg)
        store.update(job_id, progress=65, message="Building baseline story")
        timeline = build_baseline_story(evidence)
        result = {"clips": [item.model_dump() for item in evidence], "timeline": timeline.model_dump()}
        (project_dir / "analysis.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        store.update(job_id, status="completed", progress=100, message="Analysis completed", result=result)
        return result
    except Exception as exc:
        store.update(job_id, status="failed", progress=100, message="Analysis failed", error=str(exc))
        raise
