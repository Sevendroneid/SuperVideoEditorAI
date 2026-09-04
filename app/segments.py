from pathlib import Path

import cv2

from .models import ClipEvidence


def _frame_score(frame) -> float:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    sharpness_score = min(sharpness / 500.0, 1.0)
    brightness = float(gray.mean())
    exposure_score = max(0.0, 1.0 - abs(brightness - 128.0) / 128.0)
    return (sharpness_score * 0.65) + (exposure_score * 0.35)


def extract_segments(path: Path, clip: ClipEvidence, window_seconds: float = 4.0) -> list[dict]:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        return []
    fps = float(capture.get(cv2.CAP_PROP_FPS) or clip.fps or 0)
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or clip.frame_count or 0)
    duration = clip.duration_seconds
    if fps <= 0 or frame_count <= 0 or duration <= 0:
        capture.release()
        return []

    segments = []
    start = 0.0
    while start < duration:
        end = min(start + window_seconds, duration)
        midpoint = (start + end) / 2.0
        capture.set(cv2.CAP_PROP_POS_MSEC, midpoint * 1000.0)
        ok, frame = capture.read()
        if ok:
            segments.append({
                "clip_path": str(path),
                "start_seconds": round(start, 3),
                "end_seconds": round(end, 3),
                "duration_seconds": round(end - start, 3),
                "score": round(_frame_score(frame), 4),
                "evidence": ["sampled_midpoint", "sharpness", "exposure"],
            })
        start = end
    capture.release()
    return segments
