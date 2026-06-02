"""Learning Retention / Decay Model (V2).

Models knowledge per concept with a spaced-repetition forgetting curve. Each
exposure (memory touching a skill/project) is a rehearsal; memory stability
grows with the number and spread of rehearsals, and retention decays
exponentially with time since last use:

    retention(t) = exp(-idle_days / stability)

From that it derives knowledge level, retention, usage frequency, learning
velocity and a decay rate, then classifies each concept (mastered / learning /
forgotten / weak foundation / bottleneck / dormant).

`model_concept()` / `build_learning()` are pure and unit-testable; `build(db)`
feeds them per-concept exposure stats from the Memory store.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

K_REPS = 8.0       # reps for ~0.63 knowledge level (diminishing returns)
S0_DAYS = 14.0     # base memory stability in days


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _conf(n: float, scale: float, base: float = 0.3, cap: float = 0.9) -> float:
    return round(min(cap, base + n / scale), 2)


@dataclass
class ConceptLearning:
    concept: str
    knowledge_level: float    # 0..1 depth reached
    retention: float          # 0..1 estimated retained right now
    usage_frequency: float    # exposures per week over its life
    learning_velocity: float  # exposures per week recently
    decay_rate: float         # fraction lost over 30 idle days
    half_life_days: int       # time to forget half, given current stability
    status: str
    explanation: str
    evidence: dict = field(default_factory=dict)


def _stability(reps: int, span_days: float) -> float:
    """Memory stability grows with rehearsal count and how well-spaced it was."""
    spacing = 1 + min(1.0, span_days / 180) * 0.6
    return S0_DAYS * (1 + math.log1p(max(reps, 0))) * spacing


def model_concept(
    name: str,
    reps: int,
    idle_days: float,
    span_days: float,
    recent_reps: int,
    recent_window_days: int = 30,
) -> ConceptLearning:
    level = round(1 - math.exp(-reps / K_REPS), 3)
    stability = _stability(reps, span_days)
    retention = round(max(0.0, min(1.0, math.exp(-idle_days / stability))), 3)
    half_life = int(round(stability * math.log(2)))
    decay_rate = round(1 - math.exp(-30 / stability), 3)
    usage_freq = round(reps / max(span_days / 7, 1), 2)
    velocity = round(recent_reps / max(recent_window_days / 7, 1), 2)

    if level >= 0.7 and retention >= 0.6:
        status = "mastered"
    elif level >= 0.4 and retention < 0.35:
        status = "forgotten"
    elif velocity >= 2 and level < 0.45:
        status = "bottleneck"        # heavy recent effort, not yet sticking
    elif usage_freq >= 1.0 and level < 0.45:
        status = "weak_foundation"   # relied on but never learned deeply
    elif recent_reps > 0:
        status = "learning"
    else:
        status = "dormant"

    blurb = {
        "mastered": "well-practised and still strongly retained",
        "forgotten": "was learned but has likely faded without recent use",
        "bottleneck": "getting lots of recent effort but not consolidating yet",
        "weak_foundation": "used regularly but never built to depth",
        "learning": "actively being acquired",
        "dormant": "untouched and slowly decaying",
    }[status]
    return ConceptLearning(
        concept=name,
        knowledge_level=level,
        retention=retention,
        usage_frequency=usage_freq,
        learning_velocity=velocity,
        decay_rate=decay_rate,
        half_life_days=half_life,
        status=status,
        explanation=(
            f"'{name}' is {blurb}: {reps} exposure(s), last used {int(idle_days)} day(s) ago; "
            f"retention ~{round(retention * 100)}% (half-life ~{half_life}d)."
        ),
        evidence={"reps": reps, "idle_days": int(idle_days), "stability_days": round(stability, 1)},
    )


def build_learning(concepts: list[dict], recent_window_days: int = 30) -> dict:
    """`concepts`: [{name, reps, idle_days, span_days, recent_reps}]."""
    models = [
        model_concept(
            c["name"], int(c["reps"]), float(c["idle_days"]),
            float(c["span_days"]), int(c.get("recent_reps", 0)), recent_window_days,
        )
        for c in concepts
    ]
    # Most at-risk first (lowest retention).
    models.sort(key=lambda m: m.retention)
    by_status: dict[str, list[str]] = {}
    for m in models:
        by_status.setdefault(m.status, []).append(m.concept)

    return {
        "ready": bool(models),
        "concept_count": len(models),
        "status_counts": {k: len(v) for k, v in by_status.items()},
        "forgotten": by_status.get("forgotten", []),
        "weak_foundations": by_status.get("weak_foundation", []),
        "bottlenecks": by_status.get("bottleneck", []),
        "mastered": by_status.get("mastered", []),
        "concepts": [m.__dict__ for m in models],
    }


# --- DB adapter -------------------------------------------------------------
def build(db, recent_window_days: int = 30) -> dict:
    from datetime import timedelta
    from sqlalchemy import distinct, func, select
    from .models import Entity, Memory, MemoryEntity

    now = _now()
    since = now - timedelta(days=recent_window_days)

    rows = db.execute(
        select(
            Entity.id,
            Entity.name,
            func.count(MemoryEntity.memory_id).label("reps"),
            func.min(Memory.ts).label("first_seen"),
            func.max(Memory.ts).label("last_seen"),
        )
        .join(MemoryEntity, MemoryEntity.entity_id == Entity.id)
        .join(Memory, Memory.id == MemoryEntity.memory_id)
        .where(Entity.type.in_(("skill", "project")))
        .group_by(Entity.id)
    ).all()

    if not rows:
        return {"generated_at": now.isoformat(), "ready": False,
                "message": "No concepts tracked yet to model learning."}

    concepts = []
    for eid, name, reps, first_seen, last_seen in rows:
        recent = db.execute(
            select(func.count(distinct(Memory.id)))
            .join(MemoryEntity, MemoryEntity.memory_id == Memory.id)
            .where(MemoryEntity.entity_id == eid, Memory.ts >= since)
        ).scalar_one()
        concepts.append({
            "name": name,
            "reps": reps,
            "idle_days": (now - last_seen).days,
            "span_days": max((last_seen - first_seen).days, 0),
            "recent_reps": recent,
        })

    result = build_learning(concepts, recent_window_days)
    result["generated_at"] = now.isoformat()
    result["confidence"] = _conf(sum(c["reps"] for c in concepts), 80)
    result["note"] = "Spaced-repetition estimate of retention. Descriptive, not a test score."
    return result
