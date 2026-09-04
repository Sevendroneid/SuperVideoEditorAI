from app.models import SegmentEvidence
from app.story import build_baseline_story


def segment(name: str, start: float, end: float, score: float) -> SegmentEvidence:
    return SegmentEvidence(clip_path=f"/tmp/{name}.mp4", start_seconds=start, end_seconds=end, duration_seconds=end-start, score=score, evidence=["sharpness"])


def test_story_is_deterministic_and_respects_duration():
    result = build_baseline_story([segment("a", 0, 4, .9), segment("b", 0, 5, .8), segment("c", 0, 8, .7)], max_duration=10)
    assert result.total_duration_seconds == 10
    assert [item.role for item in result.items] == ["establish", "action", "detail"]
    assert result.items[-1].end_seconds == 1


def test_empty_story_is_valid():
    result = build_baseline_story([], max_duration=60)
    assert result.items == []
    assert result.total_duration_seconds == 0
