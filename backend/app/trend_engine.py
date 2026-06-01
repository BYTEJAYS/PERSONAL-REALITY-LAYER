"""Long-term Trend Engine.

Tracks how the person changes over time: which interests are rising or fading,
which skills are growing, what's newly emerging or going dormant — and rolls it
into an evolution report. Compares recent activity against a prior window.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Entity, Memory, MemoryEntity


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _window_counts(db: Session, days_from: int, days_to: int) -> dict[str, int]:
    now = _now()
    rows = db.execute(
        select(Entity.name, func.count(MemoryEntity.memory_id))
        .join(MemoryEntity, MemoryEntity.entity_id == Entity.id)
        .join(Memory, Memory.id == MemoryEntity.memory_id)
        .where(Entity.type == "skill",
               Memory.ts >= now - timedelta(days=days_from),
               Memory.ts < now - timedelta(days=days_to))
        .group_by(Entity.name)
    ).all()
    return {name: c for name, c in rows}


def _seen(db: Session) -> dict[str, tuple[datetime, datetime]]:
    rows = db.execute(
        select(Entity.name, func.min(Memory.ts), func.max(Memory.ts))
        .join(MemoryEntity, MemoryEntity.entity_id == Entity.id)
        .join(Memory, Memory.id == MemoryEntity.memory_id)
        .where(Entity.type == "skill").group_by(Entity.name)
    ).all()
    return {name: (mn, mx) for name, mn, mx in rows}


def build(db: Session, window_days: int = 30) -> dict:
    now = _now()
    recent = _window_counts(db, window_days, 0)
    prior = _window_counts(db, window_days * 2, window_days)
    seen = _seen(db)

    rising, fading, emerging, dormant = [], [], [], []
    for name, (mn, mx) in seen.items():
        r = recent.get(name, 0)
        p = prior.get(name, 0)
        if (now - mn).days <= window_days:
            emerging.append({"skill": name, "first_seen": mn.isoformat(), "recent": r})
        if r > p and r >= 2:
            rising.append({"skill": name, "recent": r, "prior": p, "delta": r - p})
        elif p >= 2 and r < p * 0.5:
            fading.append({"skill": name, "recent": r, "prior": p, "delta": r - p})
        if (now - mx).days > window_days * 2:
            dormant.append({"skill": name, "last_seen": mx.isoformat(),
                            "days_idle": (now - mx).days})

    rising.sort(key=lambda x: x["delta"], reverse=True)
    fading.sort(key=lambda x: x["delta"])
    dormant.sort(key=lambda x: x["days_idle"], reverse=True)

    return {
        "generated_at": now.isoformat(),
        "window_days": window_days,
        "rising": rising[:8],
        "fading": fading[:8],
        "emerging": emerging[:8],
        "dormant": dormant[:8],
        "report": _report(rising, fading, emerging, dormant, window_days),
    }


def _report(rising, fading, emerging, dormant, w) -> str:
    if not (rising or fading or emerging or dormant):
        return "Not enough history yet to chart how you're changing. Keep feeding the engine."
    parts = []
    if rising:
        parts.append("Growing: " + ", ".join(x["skill"] for x in rising[:3]) + ".")
    if emerging:
        parts.append("Newly emerging: " + ", ".join(x["skill"] for x in emerging[:3]) + ".")
    if fading:
        parts.append("Cooling off: " + ", ".join(x["skill"] for x in fading[:3]) + ".")
    if dormant:
        parts.append("Gone dormant: " + ", ".join(x["skill"] for x in dormant[:3]) + ".")
    return f"Over the last {w} days vs the previous {w}: " + " ".join(parts)
