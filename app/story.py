from .models import ClipEvidence, Timeline, TimelineItem


def build_baseline_story(clips: list[ClipEvidence], max_duration: float = 60.0) -> Timeline:
    """Build a deterministic first-cut story from verified clip evidence.

    This is intentionally not presented as cinematic intelligence. It is the
    reproducible baseline against which later AI Director decisions can be tested.
    """
    selected: list[TimelineItem] = []
    elapsed = 0.0
    roles = ["establish", "action", "detail", "reveal", "resolution"]
    for index, clip in enumerate(clips):
        remaining = max_duration - elapsed
        if remaining <= 0:
            break
        duration = min(clip.duration_seconds, remaining)
        if duration <= 0:
            continue
        selected.append(TimelineItem(
            clip_path=clip.path,
            start_seconds=0.0,
            end_seconds=duration,
            role=roles[index] if index < len(roles) else "unknown",
        ))
        elapsed += duration

    return Timeline(items=selected, total_duration_seconds=round(elapsed, 3))
