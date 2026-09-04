from .models import SegmentEvidence, Timeline, TimelineItem


def build_baseline_story(segments: list[SegmentEvidence], max_duration: float = 60.0) -> Timeline:
    """Build a reproducible first cut from verified segment evidence."""
    candidates = sorted(segments, key=lambda item: item.score, reverse=True)
    selected: list[TimelineItem] = []
    elapsed = 0.0
    roles = ["establish", "action", "detail", "reveal", "resolution"]
    used_ranges: set[tuple[str, float, float]] = set()

    for segment in candidates:
        if elapsed >= max_duration:
            break
        key = (segment.clip_path, segment.start_seconds, segment.end_seconds)
        if key in used_ranges:
            continue
        duration = min(segment.duration_seconds, max_duration - elapsed)
        if duration <= 0:
            continue
        selected.append(TimelineItem(
            clip_path=segment.clip_path,
            start_seconds=segment.start_seconds,
            end_seconds=round(segment.start_seconds + duration, 3),
            role=roles[len(selected)] if len(selected) < len(roles) else "unknown",
        ))
        used_ranges.add(key)
        elapsed += duration

    return Timeline(items=selected, total_duration_seconds=round(elapsed, 3))
