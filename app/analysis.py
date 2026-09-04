from pathlib import Path

from .ffmpeg import FFmpeg, FFmpegError
from .models import ClipEvidence


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}


def _fps(stream: dict) -> float:
    value = stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "0/1"
    try:
        numerator, denominator = value.split("/")
        return float(numerator) / float(denominator) if float(denominator) else 0.0
    except (ValueError, ZeroDivisionError):
        return 0.0


def inspect_clip(path: Path, ffmpeg: FFmpeg) -> ClipEvidence:
    probe = ffmpeg.probe(path)
    streams = probe.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not video:
        raise FFmpegError(f"No video stream found in {path.name}")
    fmt = probe.get("format", {})
    duration = float(fmt.get("duration") or video.get("duration") or 0)
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    frames = int(float(video.get("nb_frames") or 0)) if str(video.get("nb_frames", "")).replace(".", "", 1).isdigit() else 0
    fps = _fps(video)

    # Deterministic baseline: longer usable clips and adequate resolution score higher.
    duration_score = min(duration / 20.0, 1.0)
    resolution_score = min((width * height) / (1920 * 1080), 1.0) if width and height else 0.0
    score = round((duration_score * 0.45) + (resolution_score * 0.55), 4)
    reasons = []
    if duration >= 2:
        reasons.append("usable_duration")
    if width >= 1280 and height >= 720:
        reasons.append("hd_or_better")
    if fps > 0:
        reasons.append("valid_frame_rate")

    return ClipEvidence(
        path=str(path), filename=path.name, duration_seconds=round(duration, 3), width=width,
        height=height, fps=round(fps, 3), frame_count=frames, score=score, reasons=reasons
    )


def analyze_directory(directory: Path, ffmpeg: FFmpeg) -> list[ClipEvidence]:
    clips = sorted(p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS)
    evidence = []
    for path in clips:
        try:
            evidence.append(inspect_clip(path, ffmpeg))
        except FFmpegError:
            continue
    return sorted(evidence, key=lambda item: item.score, reverse=True)
