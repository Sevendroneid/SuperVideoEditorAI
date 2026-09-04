from app.models import ClipEvidence
from app.story import build_baseline_story


def clip(name: str, duration: float, score: float) -> ClipEvidence:
    return ClipEvidence(path=f"/tmp/{name}.mp4", filename=name, duration_seconds=duration, width=1920, height=1080, fps=30, frame_count=900, score=score, reasons=["hd_or_better"])


def test_story_is_deterministic_and_respects_duration():
    result = build_baseline_story([clip("a", 4, .9), clip("b", 5, .8), clip("c", 8, .7)], max_duration=10)
    assert result.total_duration_seconds == 10
    assert [item.role for item in result.items] == ["establish", "action", "detail"]
    assert result.items[-1].end_seconds == 1


def test_empty_story_is_valid():
    result = build_baseline_story([], max_duration=60)
    assert result.items == []
    assert result.total_duration_seconds == 0
