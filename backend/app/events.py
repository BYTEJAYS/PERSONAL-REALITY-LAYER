"""Event-Centric Memory (Memory-Architecture V3).

The storage vision says PRL must never organise life as isolated files
(``IMG_001.jpg``); it organises life into *events* — "Sister's Wedding" with its
people, span, highlights and importance. This module collapses many individual
memories into a smaller number of meaningful events.

The pure core (`cluster_events`) sessionises a time-ordered list of memories by
temporal proximity, bridging a gap when the memories share an entity (so a
multi-week project or a trip spread across days stays one event). It is fully
unit-testable; `build(db)` derives the items from the Memory + Entity store.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class EventItem:
    """One raw memory as fed to the clusterer."""

    id: str
    ts: datetime
    title: str
    entities: tuple[str, ...] = ()      # involved people/places/projects (names)
    importance: float = 0.5


@dataclass
class Event:
    title: str
    start: datetime
    end: datetime
    span_days: int
    size: int                            # how many memories collapsed into this
    importance: float
    people: list[str] = field(default_factory=list)
    highlights: list[str] = field(default_factory=list)
    memory_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "title": self.title,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "span_days": self.span_days,
            "size": self.size,
            "importance": round(self.importance, 3),
            "people": self.people,
            "highlights": self.highlights,
            "memory_ids": self.memory_ids,
        }


def _build_event(group: list[EventItem]) -> Event:
    group = sorted(group, key=lambda it: it.ts)
    start, end = group[0].ts, group[-1].ts

    # Entities that recur across the event define what it was "about".
    counts: Counter[str] = Counter()
    for it in group:
        counts.update(set(it.entities))
    dominant = [name for name, n in counts.most_common() if n >= max(2, len(group) * 0.4)]

    top = sorted(group, key=lambda it: it.importance, reverse=True)
    highlights = [it.title for it in top[: min(3, len(top))]]

    # Title: lead with the dominant entity when there is one, else the peak memory.
    if dominant:
        label = ", ".join(dominant[:2])
        title = f"{label} · {start.date():%b %Y}"
    else:
        title = top[0].title

    return Event(
        title=title,
        start=start,
        end=end,
        span_days=(end - start).days,
        size=len(group),
        importance=max(it.importance for it in group),
        people=dominant,
        highlights=highlights,
        memory_ids=[it.id for it in group],
    )


def cluster_events(
    items: list[EventItem],
    gap_days: float = 2.0,
    bridge_days: float = 30.0,
) -> list[Event]:
    """Group memories into events.

    A memory continues the current event when it is within ``gap_days`` of the
    event's most recent memory, OR within ``bridge_days`` while sharing at least
    one entity with the event (the same trip/project resurfacing). Otherwise it
    opens a new event. Returns events sorted by importance then recency.
    """
    if not items:
        return []

    ordered = sorted(items, key=lambda it: it.ts)
    events: list[list[EventItem]] = []
    cur: list[EventItem] = [ordered[0]]
    cur_entities: set[str] = set(ordered[0].entities)

    for it in ordered[1:]:
        gap = (it.ts - cur[-1].ts).total_seconds() / 86400.0
        shares = bool(cur_entities & set(it.entities))
        if gap <= gap_days or (shares and gap <= bridge_days):
            cur.append(it)
            cur_entities |= set(it.entities)
        else:
            events.append(cur)
            cur = [it]
            cur_entities = set(it.entities)
    events.append(cur)

    built = [_build_event(g) for g in events]
    built.sort(key=lambda e: (e.importance, e.end), reverse=True)
    return built


# --- DB adapter -------------------------------------------------------------
def build(db, limit: int = 2000) -> dict:
    from sqlalchemy import select
    from .models import Entity, Memory, MemoryEntity

    rows = db.execute(
        select(Memory.id, Memory.ts, Memory.title, Memory.importance)
        .order_by(Memory.ts)
        .limit(limit)
    ).all()

    # Entity names per memory in one pass.
    ent_rows = db.execute(
        select(MemoryEntity.memory_id, Entity.name).join(
            Entity, Entity.id == MemoryEntity.entity_id
        )
    ).all()
    by_mem: dict = {}
    for mid, name in ent_rows:
        by_mem.setdefault(mid, []).append(name)

    items = [
        EventItem(
            id=str(mid),
            ts=ts,
            title=title,
            entities=tuple(by_mem.get(mid, ())),
            importance=imp if imp is not None else 0.5,
        )
        for mid, ts, title, imp in rows
    ]
    events = cluster_events(items)
    multi = [e for e in events if e.size > 1]

    return {
        "generated_at": _now().isoformat(),
        "ready": len(events) > 0,
        "memories_in": len(items),
        "events_out": len(events),
        "compaction": round(1 - len(events) / len(items), 3) if items else 0.0,
        "multi_memory_events": len(multi),
        "events": [e.as_dict() for e in events[:200]],
    }
