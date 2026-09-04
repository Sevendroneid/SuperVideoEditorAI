import json
from pathlib import Path

from celery import Celery

from .analysis import analyze_directory
from .config import get_settings
from .ffmpeg import FFmpeg
from .jobs import JobStore
from .models import SegmentEvidence
from .segments import extract_segments
from .story import build_baseline_story

settings = get_settings()
celery_app = Celery("supervideoeditorai", broker=settings.redis_url, backend=settings.celery_result_backend)
celery_app.conf.update(
    task_serializer="json", result_serializer="json", accept_content=["json"],
    task_track_started=True, task_time_limit=3600, task_soft_time_limit=3300,
)


@celery_app.task(bind=True, name="analyze_project")
def analyze_project(self, job_id: str, project_id: str) -> dict:
    store = JobStore(settings.projects_dir / project_id / "jobs")
    project_dir = settings.projects_dir / project_id
    try:
        store.update(job_id, status="processing", progress=10, message="Inspecting video files")
        ffmpeg = FFmpeg(settings.ffmpeg_bin, settings.ffprobe_bin)
        clips = analyze_directory(project_dir, ffmpeg)
        store.update(job_id, progress=40, message="Scoring smart segments")
        segments: list[SegmentEvidence] = []
        for clip in clips:
            segments.extend(SegmentEvidence.model_validate(item) for item in extract_segments(Path(clip.path), clip))
        store.update(job_id, progress=70, message="Building baseline story")
        timeline = build_baseline_story(segments)
        result = {
            "clips": [item.model_dump() for item in clips],
            "segments": [item.model_dump() for item in segments],
            "timeline": timeline.model_dump(),
        }
        (project_dir / "analysis.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        store.update(job_id, status="completed", progress=100, message="Analysis completed", result=result)
        return result
    except Exception as exc:
        store.update(job_id, status="failed", progress=100, message="Analysis failed", error=str(exc))
        raise


@celery_app.task(bind=True, name="render_project")
def render_project(self, job_id: str, project_id: str) -> dict:
    project_dir = settings.projects_dir / project_id
    store = JobStore(project_dir / "jobs")
    work_dir = project_dir / "render_segments"
    try:
        store.update(job_id, status="processing", progress=10, message="Preparing timeline segments")
        analysis = json.loads((project_dir / "analysis.json").read_text(encoding="utf-8"))
        items = analysis.get("timeline", {}).get("items", [])
        if not items:
            raise RuntimeError("Timeline contains no clips")
        ffmpeg = FFmpeg(settings.ffmpeg_bin, settings.ffprobe_bin)
        work_dir.mkdir(parents=True, exist_ok=True)
        rendered = []
        for index, item in enumerate(items):
            source = Path(item["clip_path"])
            if not source.is_file():
                raise RuntimeError(f"Timeline references missing clip: {source.name}")
            target = work_dir / f"segment_{index:04d}.mp4"
            ffmpeg.extract_segment(source, float(item["start_seconds"]), float(item["end_seconds"]), target)
            rendered.append(target)
            store.update(job_id, progress=min(90, 10 + int((index + 1) / len(items) * 80)), message=f"Rendered segment {index + 1}/{len(items)}")
        output = settings.outputs_dir / f"{project_id}.mp4"
        ffmpeg.concat(rendered, output)
        result = {"output": str(output), "segments_rendered": len(rendered)}
        store.update(job_id, status="completed", progress=100, message="Render completed", result=result)
        return result
    except Exception as exc:
        store.update(job_id, status="failed", progress=100, message="Render failed", error=str(exc))
        raise
