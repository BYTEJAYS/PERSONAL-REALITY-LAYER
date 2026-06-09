"""Habits connector — learn from habits tracked in ASCENSION (the life-RPG).

ASCENSION records, per habit, the exact dates it was completed. We turn each
completion into one backdated memory linked to a `habit` entity, so PRL's
behavioural engines (habit_genome, cognitive_model productivity, brain) see the
real time-series — when a habit formed, grew, stayed stable, or went dormant.

Idempotent: every completion carries a stable dedupe_key, so the full history can
be pushed on every sync and PRL only stores dates it hasn't seen.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .. import memory_engine
from ..memory_engine import EntityRef, MemoryInput


def _parse_date(d: str) -> datetime | None:
    try:
        return datetime.strptime(str(d)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _slug(name: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")


def ingest_habits(db: Session, habits: list[dict]) -> dict:
    """Ingest a list of habits with their completion-date histories.

    Each habit dict: {name, dates: [YYYY-MM-DD], stat?, category?, frequency?,
    priority?, notes?, streak?, best_streak?}.
    """
    items: list[MemoryInput] = []
    names: list[str] = []

    for h in habits:
        name = (h.get("name") or "").strip()
        if not name:
            continue
        names.append(name)

        stat = (h.get("stat") or "").strip()
        cadence = (h.get("frequency") or h.get("category") or "").strip()
        try:
            priority = int(h.get("priority") or 1)
        except (ValueError, TypeError):
            priority = 1
        importance = min(0.9, 0.5 + 0.1 * priority)
        notes = (h.get("notes") or "").strip()
        slug = _slug(name)

        for d in h.get("dates") or []:
            ts = _parse_date(d)
            if ts is None:
                continue
            bits = [f"Kept up the habit '{name}'."]
            if stat:
                bits.append(f"Builds {stat}.")
            if cadence:
                bits.append(f"Cadence: {cadence}.")
            if notes:
                bits.append(notes)
            items.append(
                MemoryInput(
                    ts=ts,
                    source="habit",
                    title=f"Habit: {name}",
                    content=" ".join(bits),
                    importance=importance,
                    memory_type="episodic",
                    entities=[EntityRef(type="habit", name=name, role="habit")],
                    dedupe_key=f"ascension:habit:{slug}:{str(d)[:10]}",
                )
            )

    result = memory_engine.ingest_many(db, items)
    result["habits"] = sorted(set(names))
    return result
