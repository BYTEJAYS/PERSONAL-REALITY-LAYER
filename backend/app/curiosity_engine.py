"""Curiosity Engine + Missing-Memory Detector (Reality OS).

PRL should not sit passive. It notices what it doesn't yet understand — an
unnamed face that keeps recurring, a cluster of hospital visits, a blank stretch
of years — and asks the user, turning gaps into questions that improve the model
over time.

Pure detectors are DB-free and unit-testable; ``build(db)`` derives the signals
(entity mentions, topic clusters, timeline coverage) from the store.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

UNIDENTIFIED_MIN_MENTIONS = 4
TOPIC_MIN_MENTIONS = 5
GAP_MIN_YEARS = 2


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Question:
    text: str
    kind: str            # identify | organise | health | gap
    priority: float      # 0..1
    evidence: str = ""

    def as_dict(self) -> dict:
        return {"text": self.text, "kind": self.kind,
                "priority": round(self.priority, 3), "evidence": self.evidence}


def detect_gaps(years: list[int], min_gap: int = GAP_MIN_YEARS) -> list[tuple[int, int]]:
    """Stretches of ≥`min_gap` empty years between recorded activity."""
    ys = sorted(set(years))
    gaps = []
    for a, b in zip(ys, ys[1:]):
        if b - a > min_gap:
            gaps.append((a + 1, b - 1))
    return gaps


def from_unidentified_people(people: list[dict]) -> list[Question]:
    """`people` = [{name, mentions, identified}]. Frequent-but-unknown → ask who."""
    out = []
    for p in people:
        if not p.get("identified", False) and p.get("mentions", 0) >= UNIDENTIFIED_MIN_MENTIONS:
            out.append(Question(
                text=f"I keep seeing “{p['name']}” ({p['mentions']} times). Who are they to you?",
                kind="identify",
                priority=min(1.0, 0.4 + p["mentions"] / 20.0),
                evidence=f"{p['mentions']} mentions",
            ))
    return out


def from_repeated_topics(topics: list[dict]) -> list[Question]:
    """`topics` = [{name, mentions, kind}]. Frequent topics → offer a dedicated space."""
    out = []
    for t in topics:
        if t.get("mentions", 0) < TOPIC_MIN_MENTIONS:
            continue
        if t.get("kind") == "health":
            out.append(Question(
                text=f"I noticed repeated health mentions around “{t['name']}”. "
                     "Want me to build a health timeline?",
                kind="health", priority=0.8, evidence=f"{t['mentions']} mentions"))
        else:
            out.append(Question(
                text=f"You often mention “{t['name']}”. Should I create a dedicated "
                     "memory space for it?",
                kind="organise",
                priority=min(0.9, 0.4 + t["mentions"] / 25.0),
                evidence=f"{t['mentions']} mentions"))
    return out


def from_gaps(years: list[int]) -> list[Question]:
    out = []
    for a, b in detect_gaps(years):
        span = b - a + 1
        out.append(Question(
            text=f"Your timeline is blank from {a} to {b}. Can you fill in those years?",
            kind="gap", priority=min(1.0, 0.5 + span / 10.0),
            evidence=f"{span} missing year(s)"))
    return out


def synthesize(people: list[dict], topics: list[dict], years: list[int]) -> list[Question]:
    qs = from_unidentified_people(people) + from_repeated_topics(topics) + from_gaps(years)
    qs.sort(key=lambda q: -q.priority)
    return qs


# --- DB adapter -------------------------------------------------------------
def build(db) -> dict:
    from sqlalchemy import func, select
    from .models import Entity, Memory, MemoryEntity

    # People with mention counts; "identified" if a relation was recorded in meta.
    person_rows = db.execute(
        select(Entity.name, func.count(MemoryEntity.memory_id), Entity.meta)
        .join(MemoryEntity, MemoryEntity.entity_id == Entity.id)
        .where(Entity.type == "person")
        .group_by(Entity.id)
    ).all()
    people = [{"name": n, "mentions": c,
               "identified": bool((m or {}).get("relation"))} for n, c, m in person_rows]

    # Topics = projects/skills by mention; health-flag if health records nearby.
    topic_rows = db.execute(
        select(Entity.name, Entity.type, func.count(MemoryEntity.memory_id))
        .join(MemoryEntity, MemoryEntity.entity_id == Entity.id)
        .where(Entity.type.in_(("project", "skill")))
        .group_by(Entity.id)
    ).all()
    topics = [{"name": n, "mentions": c, "kind": typ} for n, typ, c in topic_rows]

    year_rows = db.execute(select(func.extract("year", Memory.ts))).all()
    years = [int(y) for (y,) in year_rows if y is not None]

    questions = synthesize(people, topics, years)
    return {
        "ready": len(questions) > 0,
        "generated_at": _now().isoformat(),
        "question_count": len(questions),
        "gaps": [{"from": a, "to": b} for a, b in detect_gaps(years)],
        "questions": [q.as_dict() for q in questions[:30]],
    }
