from __future__ import annotations

import re
from typing import Any

from .models import SegmentEvidence, Timeline, TimelineItem


class DirectorInstructionError(ValueError):
    """Raised when a creative direction cannot be applied safely."""


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def apply_director_instruction(
    segments: list[SegmentEvidence],
    current: Timeline,
    instruction: str,
    max_duration: float = 60.0,
) -> tuple[Timeline, dict[str, Any]]:
    """Apply a small, deterministic subset of director language to a timeline.

    This is deliberately evidence-bound: it can only select segments present in the
    supplied analysis and never invents media. Unsupported instructions are reported
    instead of silently changing the edit.
    """
    text = _normalize(instruction)
    if not text:
        raise DirectorInstructionError("Instruction cannot be empty")
    if len(text) > 500:
        raise DirectorInstructionError("Instruction is too long (maximum 500 characters)")

    by_path: dict[str, list[SegmentEvidence]] = {}
    for segment in segments:
        by_path.setdefault(segment.clip_path, []).append(segment)

    candidates = sorted(segments, key=lambda item: item.score, reverse=True)
    selected = list(current.items)
    changes: list[str] = []

    if any(token in text for token in ("opening", "open", "intro")) and "strong" in text:
        strongest = candidates[:3]
        if strongest:
            first = strongest[0]
            opening = TimelineItem(
                clip_path=first.clip_path,
                start_seconds=first.start_seconds,
                end_seconds=min(first.end_seconds, first.start_seconds + min(first.duration_seconds, 4.0)),
                role="establish",
            )
            selected = [opening] + [item for item in selected if item.clip_path != opening.clip_path]
            changes.append("replaced opening with highest-scoring verified segment")

    if "drone" in text and any(token in text for token in ("less", "don't use too much", "do not use too much", "reduce")):
        drone_items = [item for item in selected if "drone" in item.clip_path.lower()]
        if drone_items:
            selected = [item for item in selected if "drone" not in item.clip_path.lower()]
            changes.append(f"removed {len(drone_items)} segment(s) whose filename identifies them as drone footage")
        else:
            changes.append("no drone-labelled timeline segment was found; timeline unchanged for this instruction")

    if any(token in text for token in ("ending", "end")) and any(token in text for token in ("calmer", "calm", "quiet")):
        calm = sorted(candidates, key=lambda item: ("resolution" in " ".join(item.evidence).lower(), -item.score), reverse=True)
        if calm:
            last = calm[0]
            closing = TimelineItem(
                clip_path=last.clip_path,
                start_seconds=last.start_seconds,
                end_seconds=min(last.end_seconds, last.start_seconds + min(last.duration_seconds, 5.0)),
                role="resolution",
            )
            selected = [item for item in selected if item.clip_path != closing.clip_path] + [closing]
            changes.append("set ending to a verified resolution candidate")

    if "shorter" in text or "shorten" in text:
        target = min(max_duration, max(5.0, current.total_duration_seconds * 0.7))
        selected, duration = _trim(selected, target)
        changes.append(f"shortened timeline to approximately {duration:.1f}s")

    if "longer" in text or "slow down" in text:
        target = min(max_duration, current.total_duration_seconds * 1.3)
        selected, duration = _extend_from_candidates(selected, candidates, target)
        changes.append(f"extended timeline to approximately {duration:.1f}s where verified footage allowed")

    if not changes:
        return current, {
            "applied": False,
            "instruction": instruction,
            "reason": "No supported deterministic director operation matched the instruction.",
            "available_operations": [
                "make the opening stronger",
                "use less drone",
                "make the ending calmer",
                "make it shorter",
                "make it longer",
            ],
        }

    selected = _dedupe(selected)
    total = round(sum(item.end_seconds - item.start_seconds for item in selected), 3)
    return Timeline(items=selected, total_duration_seconds=total), {
        "applied": True,
        "instruction": instruction,
        "changes": changes,
        "evidence_bound": True,
    }


def _dedupe(items: list[TimelineItem]) -> list[TimelineItem]:
    seen: set[tuple[str, float, float]] = set()
    result: list[TimelineItem] = []
    for item in items:
        key = (item.clip_path, item.start_seconds, item.end_seconds)
        if key not in seen and item.end_seconds > item.start_seconds:
            result.append(item)
            seen.add(key)
    return result


def _trim(items: list[TimelineItem], target: float) -> tuple[list[TimelineItem], float]:
    result: list[TimelineItem] = []
    remaining = target
    for item in items:
        if remaining <= 0:
            break
        duration = min(item.end_seconds - item.start_seconds, remaining)
        result.append(item.model_copy(update={"end_seconds": round(item.start_seconds + duration, 3)}))
        remaining -= duration
    return result, target - remaining


def _extend_from_candidates(
    items: list[TimelineItem], candidates: list[SegmentEvidence], target: float
) -> tuple[list[TimelineItem], float]:
    result = list(items)
    existing = {(item.clip_path, item.start_seconds, item.end_seconds) for item in result}
    total = sum(item.end_seconds - item.start_seconds for item in result)
    for segment in candidates:
        if total >= target:
            break
        key = (segment.clip_path, segment.start_seconds, segment.end_seconds)
        if key in existing:
            continue
        duration = min(segment.duration_seconds, target - total)
        result.append(TimelineItem(
            clip_path=segment.clip_path,
            start_seconds=segment.start_seconds,
            end_seconds=round(segment.start_seconds + duration, 3),
            role="unknown",
        ))
        existing.add(key)
        total += duration
    return result, total
