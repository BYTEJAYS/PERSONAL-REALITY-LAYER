from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import Memory

router = APIRouter(prefix="/reconstruct", tags=["reconstruct"])


@router.get("/{day}")
def reconstruct_day(day: date, db: Session = Depends(get_db)):
    """Reality Reconstruction: rebuild a single day into a narrative.

    Example: GET /reconstruct/2026-05-29
    """
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    end = datetime.combine(day, time.max, tzinfo=timezone.utc)

    rows = db.execute(
        select(Memory)
        .options(selectinload(Memory.links))
        .where(Memory.ts >= start, Memory.ts <= end)
        .order_by(Memory.ts.asc())
    ).scalars().all()

    projects: Counter = Counter()
    people: Counter = Counter()
    skills: Counter = Counter()
    sources: Counter = Counter()
    events = []

    for m in rows:
        sources[m.source] += 1
        for link in m.links:
            if link.entity.type == "project":
                projects[link.entity.name] += 1
            elif link.entity.type == "person":
                people[link.entity.name] += 1
            elif link.entity.type == "skill":
                skills[link.entity.name] += 1
        events.append({
            "ts": m.ts.isoformat(),
            "source": m.source,
            "title": m.title,
            "importance": m.importance,
        })

    narrative = _narrative(day, len(rows), projects, people, skills)

    return {
        "date": day.isoformat(),
        "memory_count": len(rows),
        "sources": dict(sources),
        "top_projects": projects.most_common(5),
        "people": people.most_common(10),
        "skills": skills.most_common(10),
        "events": events,
        "narrative": narrative,
    }


def _narrative(day, count, projects, people, skills) -> str:
    if count == 0:
        return f"No recorded activity on {day.isoformat()}."
    parts = [f"On {day.strftime('%B %d, %Y')} you generated {count} memories."]
    if projects:
        top = ", ".join(f"{n} ({c})" for n, c in projects.most_common(3))
        parts.append(f"Most of your effort went into {top}.")
    if skills:
        parts.append("You applied " + ", ".join(s for s, _ in skills.most_common(4)) + ".")
    if people:
        parts.append("People involved: " + ", ".join(p for p, _ in people.most_common(5)) + ".")
    return " ".join(parts)
