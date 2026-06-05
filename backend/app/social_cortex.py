"""Social Cortex (Ledger).

Relationship intelligence from the people who appear in a life: how often you
interact with someone, when you last did, whether a bond is growing or quietly
drifting, and an overall closeness read. Pure ``analyze`` is DB-free and
unit-testable; ``build(db)`` reads ``person`` entities and their memory links.

Observes interaction, never judges relationships. No people → ``ready: false``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

DRIFT_DAYS = 120          # a once-frequent contact unseen this long is "drifting"
RECENT_DAYS = 90          # window used to judge rising vs fading


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Interaction:
    person: str
    date: datetime
    importance: float = 0.5


@dataclass
class Person:
    name: str
    interactions: list[Interaction] = field(default_factory=list)


def _closeness(count: int, recency_days: float, weight: float) -> float:
    """0..1 blend of how often, how recently, and how weighty the contact is."""
    freq = min(1.0, count / 20.0)
    recency = max(0.0, 1.0 - recency_days / 365.0)
    wt = min(1.0, weight / 10.0)
    return round(0.5 * freq + 0.3 * recency + 0.2 * wt, 3)


def analyze(interactions: list[Interaction], today: datetime | None = None) -> dict:
    today = today or _now()
    if not interactions:
        return {"ready": False, "message": "No social interactions recorded yet."}

    people: dict[str, list[Interaction]] = {}
    for it in interactions:
        people.setdefault(it.person, []).append(it)

    cutoff = today - timedelta_days(RECENT_DAYS)
    contacts = []
    drifting = []
    for name, its in people.items():
        its = sorted(its, key=lambda x: x.date)
        first, last = its[0].date, its[-1].date
        recency_days = (today - last).days
        weight = sum(x.importance for x in its)
        recent_n = sum(1 for x in its if x.date >= cutoff)
        earlier_n = len(its) - recent_n
        # Rising if the recent window holds a disproportionate share of contact.
        if recent_n > earlier_n and recent_n >= 2:
            trend = "rising"
        elif recency_days > DRIFT_DAYS and len(its) >= 3:
            trend = "fading"
        else:
            trend = "steady"

        record = {
            "person": name,
            "interactions": len(its),
            "first_seen": first.isoformat(),
            "last_seen": last.isoformat(),
            "days_since": recency_days,
            "trend": trend,
            "closeness": _closeness(len(its), recency_days, weight),
        }
        contacts.append(record)
        if trend == "fading":
            drifting.append(record)

    contacts.sort(key=lambda c: -c["closeness"])
    drifting.sort(key=lambda c: -c["days_since"])
    inner_circle = [c["person"] for c in contacts[:5]]

    parts = [f"{len(people)} people tracked", f"{len(interactions)} interactions"]
    if inner_circle:
        parts.append("closest: " + ", ".join(inner_circle[:3]))
    if drifting:
        parts.append(f"{len(drifting)} drifting")
    return {
        "ready": True,
        "generated_at": today.isoformat(),
        "people_count": len(people),
        "interaction_count": len(interactions),
        "inner_circle": inner_circle,
        "contacts": contacts[:50],
        "drifting": drifting[:20],
        "explanation": "; ".join(parts) + ".",
    }


def timedelta_days(n: int):
    from datetime import timedelta
    return timedelta(days=n)


# --- DB adapter -------------------------------------------------------------
def build(db) -> dict:
    from sqlalchemy import select
    from .models import Entity, Memory, MemoryEntity

    rows = db.execute(
        select(Entity.name, Memory.ts, Memory.importance)
        .join(MemoryEntity, MemoryEntity.entity_id == Entity.id)
        .join(Memory, Memory.id == MemoryEntity.memory_id)
        .where(Entity.type == "person")
    ).all()
    interactions = []
    for name, ts, imp in rows:
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        interactions.append(Interaction(name, ts, imp if imp is not None else 0.5))
    return analyze(interactions)
