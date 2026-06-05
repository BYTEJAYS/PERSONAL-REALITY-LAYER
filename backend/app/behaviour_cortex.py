"""Behaviour Cortex (Ledger).

Habit and routine intelligence: when you are active across the day (focus
hours), which days of the week carry your effort, and how consistently you show
up. It reuses the shared ``rhythm`` definition so its focus window agrees with
the Cognitive Twin and Pattern Engine rather than telling a contradictory story.

Pure ``analyze`` is DB-free and unit-testable; ``build(db)`` reads memory
timestamps. No activity → ``ready: false``.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone

from .rhythm import best_window, rhythm_label, window_center

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Activity:
    ts: datetime
    importance: float = 0.5
    source: str = ""


def analyze(activities: list[Activity], today: datetime | None = None) -> dict:
    today = today or _now()
    if not activities:
        return {"ready": False, "message": "No activity recorded yet."}

    # Importance-weighted hour histogram → focus window (shared rhythm definition).
    hours = [0.0] * 24
    weekdays = [0.0] * 7
    days_seen: set[str] = set()
    for a in activities:
        ts = a.ts if a.ts.tzinfo else a.ts.replace(tzinfo=timezone.utc)
        hours[ts.hour] += a.importance
        weekdays[ts.weekday()] += a.importance
        days_seen.add(ts.date().isoformat())

    start, end, share = best_window(hours, 4)
    label = rhythm_label(window_center(start, 4))

    # Most active weekday.
    peak_wd_idx = max(range(7), key=lambda i: weekdays[i])
    wd_total = sum(weekdays) or 1.0
    weekday_profile = [
        {"day": WEEKDAYS[i], "share": round(weekdays[i] / wd_total, 3)} for i in range(7)
    ]

    # Consistency: active days across the observed span.
    dates = sorted(days_seen)
    span_days = (
        (datetime.fromisoformat(dates[-1]) - datetime.fromisoformat(dates[0])).days + 1
        if len(dates) >= 2 else 1
    )
    consistency = round(len(days_seen) / span_days, 3) if span_days else 0.0

    parts = [
        f"{len(activities)} actions across {len(days_seen)} active days",
        f"focus window {start:02d}:00–{end:02d}:00 ({label})",
        f"busiest on {WEEKDAYS[peak_wd_idx]}",
    ]
    return {
        "ready": True,
        "generated_at": today.isoformat(),
        "focus_window": {"start": start, "end": end, "share": share, "label": label},
        "peak_weekday": WEEKDAYS[peak_wd_idx],
        "weekday_profile": weekday_profile,
        "active_days": len(days_seen),
        "span_days": span_days,
        "consistency": consistency,
        "hour_histogram": [round(h, 2) for h in hours],
        "explanation": "; ".join(parts) + ".",
    }


# --- DB adapter -------------------------------------------------------------
def build(db) -> dict:
    from sqlalchemy import select
    from .models import Memory

    rows = db.execute(select(Memory.ts, Memory.importance, Memory.source)).all()
    activities = []
    for ts, imp, source in rows:
        if ts is None:
            continue
        activities.append(Activity(ts, imp if imp is not None else 0.5, source or ""))
    return analyze(activities)
