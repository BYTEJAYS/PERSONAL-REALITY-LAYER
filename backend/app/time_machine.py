"""Time Machine (Ledger).

Navigate a life across resolutions — day, month, year, decade — like Google Maps
zoom for your own past. The pure core buckets dated memories at any scale, each
bucket carrying its size and its headline (the most important moment inside it);
``build(db)`` returns all four zoom levels at once, and ``navigate`` drills into
one period.

Pure ``bucket`` is DB-free and unit-testable. No memories → ``ready: false``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

SCALES = ("day", "month", "year", "decade")


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class TimePoint:
    date: datetime
    title: str
    importance: float = 0.5


def _key(d: datetime, scale: str) -> str:
    if scale == "day":
        return f"{d.year:04d}-{d.month:02d}-{d.day:02d}"
    if scale == "month":
        return f"{d.year:04d}-{d.month:02d}"
    if scale == "year":
        return f"{d.year:04d}"
    if scale == "decade":
        return f"{(d.year // 10) * 10}s"
    raise ValueError(f"unknown scale: {scale}")


def bucket(points: list[TimePoint], scale: str) -> list[dict]:
    """Group points into `scale` buckets, newest first, each with its headline."""
    if scale not in SCALES:
        raise ValueError(f"unknown scale: {scale}")
    groups: dict[str, list[TimePoint]] = {}
    for p in points:
        groups.setdefault(_key(p.date, scale), []).append(p)

    out = []
    for key in sorted(groups, reverse=True):
        pts = groups[key]
        top = max(pts, key=lambda p: p.importance)
        out.append({
            "key": key,
            "scale": scale,
            "count": len(pts),
            "importance": round(max(p.importance for p in pts), 3),
            "headline": top.title,
            "start": min(p.date for p in pts).isoformat(),
            "end": max(p.date for p in pts).isoformat(),
        })
    return out


def in_period(points: list[TimePoint], scale: str, key: str) -> list[TimePoint]:
    return [p for p in points if _key(p.date, scale) == key]


# --- DB adapter -------------------------------------------------------------
def _load(db) -> list[TimePoint]:
    from sqlalchemy import select
    from .models import Memory

    rows = db.execute(select(Memory.ts, Memory.title, Memory.importance)).all()
    pts = []
    for ts, title, imp in rows:
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        pts.append(TimePoint(ts, title, imp if imp is not None else 0.5))
    return pts


def build(db) -> dict:
    pts = _load(db)
    if not pts:
        return {"ready": False, "message": "No memories to navigate yet."}
    return {
        "ready": True,
        "generated_at": _now().isoformat(),
        "total_memories": len(pts),
        "views": {scale: bucket(pts, scale) for scale in SCALES},
    }


def navigate(db, scale: str, key: str) -> dict:
    """Zoom into one period and list the memories inside it, newest first."""
    if scale not in SCALES:
        return {"ready": False, "error": f"unknown scale: {scale}"}
    pts = in_period(_load(db), scale, key)
    pts.sort(key=lambda p: p.date, reverse=True)
    return {
        "ready": len(pts) > 0,
        "generated_at": _now().isoformat(),
        "scale": scale,
        "key": key,
        "count": len(pts),
        "memories": [
            {"date": p.date.isoformat(), "title": p.title, "importance": round(p.importance, 3)}
            for p in pts[:200]
        ],
    }
