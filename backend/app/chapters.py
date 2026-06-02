"""Life Chapter Detection (V2).

Automatically segments the timeline into chapters by detecting sustained shifts
in what dominated the user's attention month to month (e.g. "Machine Learning
Phase" → "Research Phase"). The pure core works on a month→label series and is
unit-testable; `detect(db)` derives the labels from the Memory store.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Chapter:
    title: str
    theme: str
    start: str          # YYYY-MM
    end: str            # YYYY-MM
    span_months: int
    months: list[str] = field(default_factory=list)


def _smooth(labels: list[str]) -> list[str]:
    """Remove single-month blips sandwiched between two months of one theme,
    so a one-off month doesn't fragment a genuine chapter."""
    if len(labels) < 3:
        return labels[:]
    out = labels[:]
    for i in range(1, len(out) - 1):
        if out[i - 1] == out[i + 1] and out[i] != out[i - 1]:
            out[i] = out[i - 1]
    return out


def detect_chapters(monthly: list[tuple[str, str]], min_months: int = 2) -> list[Chapter]:
    """`monthly` is an ordered list of (YYYY-MM, dominant_label). Consecutive
    months sharing a label merge into one chapter; sub-`min_months` chapters are
    folded into a neighbour so only sustained phases surface."""
    if not monthly:
        return []
    months = [m for m, _ in monthly]
    labels = _smooth([lbl for _, lbl in monthly])

    # Merge consecutive equal labels into runs.
    runs: list[Chapter] = []
    start_i = 0
    for i in range(1, len(labels) + 1):
        if i == len(labels) or labels[i] != labels[start_i]:
            seg = months[start_i:i]
            runs.append(
                Chapter(
                    title=f"{labels[start_i]} Phase",
                    theme=labels[start_i],
                    start=seg[0],
                    end=seg[-1],
                    span_months=len(seg),
                    months=seg,
                )
            )
            start_i = i

    if len(runs) <= 1:
        return runs

    # Fold tiny chapters into the larger adjacent neighbour.
    merged: list[Chapter] = []
    for ch in runs:
        if ch.span_months < min_months and merged:
            prev = merged[-1]
            prev.end = ch.end
            prev.months += ch.months
            prev.span_months = len(prev.months)
        else:
            merged.append(ch)
    return merged


# --- DB adapter -------------------------------------------------------------
def detect(db) -> dict:
    from collections import Counter
    from sqlalchemy import func, select
    from .models import Entity, Memory, MemoryEntity

    # Dominant project/skill per month (by linked-memory count).
    rows = db.execute(
        select(
            func.to_char(Memory.ts, "YYYY-MM").label("ym"),
            Entity.name,
            func.count(MemoryEntity.memory_id).label("n"),
        )
        .join(MemoryEntity, MemoryEntity.memory_id == Memory.id)
        .join(Entity, Entity.id == MemoryEntity.entity_id)
        .where(Entity.type.in_(("project", "skill")))
        .group_by("ym", Entity.name)
    ).all()

    by_month: dict[str, Counter] = {}
    for ym, name, n in rows:
        by_month.setdefault(ym, Counter())[name] += n

    monthly = [(ym, by_month[ym].most_common(1)[0][0]) for ym in sorted(by_month)]
    chapters = detect_chapters(monthly)

    return {
        "generated_at": _now().isoformat(),
        "ready": len(chapters) > 0,
        "months_observed": len(monthly),
        "chapters": [c.__dict__ for c in chapters],
        "current_chapter": chapters[-1].__dict__ if chapters else None,
    }
