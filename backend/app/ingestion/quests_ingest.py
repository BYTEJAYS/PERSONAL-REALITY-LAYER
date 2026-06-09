"""Quests connector — completed quests from ASCENSION (the life-RPG).

Unlike habits (a recurring time-series → habit entities), a quest is a one-off
accomplishment. Each completed quest becomes a single backdated episodic memory
at its completion date, so it contributes to PRL's real active-day signal and
shows up in the timeline / reconstruction / insights.

Idempotent: each quest carries a stable dedupe_key (its ASCENSION id), so the
full completed-quest list can be pushed every sync and PRL only stores new ones.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .. import memory_engine
from ..memory_engine import MemoryInput


def _parse_date(d: str) -> datetime | None:
    try:
        return datetime.strptime(str(d)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def ingest_quests(db: Session, quests: list[dict]) -> dict:
    """Ingest completed quests.

    Each quest dict: {id, title, completed_at: YYYY-MM-DD, description?, stat?,
    type?, xp?}.
    """
    items: list[MemoryInput] = []
    titles: list[str] = []

    for q in quests:
        qid = (q.get("id") or "").strip()
        title = (q.get("title") or "").strip()
        ts = _parse_date(q.get("completed_at") or "")
        if not qid or not title or ts is None:
            continue
        titles.append(title)

        try:
            xp = int(q.get("xp") or 0)
        except (ValueError, TypeError):
            xp = 0
        importance = min(0.85, 0.45 + xp / 500.0)

        bits = [f"Completed the quest '{title}'."]
        if q.get("description"):
            bits.append(str(q["description"]))
        if q.get("stat"):
            bits.append(f"Builds {str(q['stat']).strip()}.")
        if q.get("type"):
            bits.append(f"({str(q['type']).strip()} quest)")

        items.append(
            MemoryInput(
                ts=ts,
                source="quest",
                title=f"Quest: {title}",
                content=" ".join(bits),
                importance=importance,
                memory_type="episodic",
                dedupe_key=f"ascension:quest:{qid}",
            )
        )

    result = memory_engine.ingest_many(db, items)
    result["quests"] = len(titles)
    return result
