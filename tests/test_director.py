import pytest

from app.director import DirectorInstructionError, apply_director_instruction
from app.models import SegmentEvidence, Timeline, TimelineItem


def segments():
    return [
        SegmentEvidence(clip_path="arrival.mp4", start_seconds=0, end_seconds=4, duration_seconds=4, score=0.8, evidence=["stable"]),
        SegmentEvidence(clip_path="drone_sky.mp4", start_seconds=0, end_seconds=5, duration_seconds=5, score=0.95, evidence=["wide"]),
        SegmentEvidence(clip_path="door.mp4", start_seconds=1, end_seconds=5, duration_seconds=4, score=0.9, evidence=["action"]),
        SegmentEvidence(clip_path="sunset.mp4", start_seconds=2, end_seconds=7, duration_seconds=5, score=0.85, evidence=["resolution"]),
    ]


def timeline():
    return Timeline(items=[
        TimelineItem(clip_path="drone_sky.mp4", start_seconds=0, end_seconds=5, role="establish"),
        TimelineItem(clip_path="door.mp4", start_seconds=1, end_seconds=5, role="action"),
    ], total_duration_seconds=9)


def test_strong_opening_uses_verified_evidence():
    result, meta = apply_director_instruction(segments(), timeline(), "Make the opening stronger")
    assert meta["applied"] is True
    assert result.items[0].clip_path == "drone_sky.mp4"
    assert result.items[0].role == "establish"


def test_less_drone_removes_drone_filename():
    result, meta = apply_director_instruction(segments(), timeline(), "Use less drone")
    assert meta["applied"] is True
    assert all("drone" not in item.clip_path.lower() for item in result.items)


def test_shorter_never_exceeds_target():
    result, _ = apply_director_instruction(segments(), timeline(), "Make it shorter")
    assert result.total_duration_seconds <= 9
    assert result.total_duration_seconds >= 5


def test_empty_instruction_rejected():
    with pytest.raises(DirectorInstructionError):
        apply_director_instruction(segments(), timeline(), "   ")


def test_unsupported_instruction_is_transparent():
    result, meta = apply_director_instruction(segments(), timeline(), "Make the colors more nostalgic")
    assert result == timeline()
    assert meta["applied"] is False
