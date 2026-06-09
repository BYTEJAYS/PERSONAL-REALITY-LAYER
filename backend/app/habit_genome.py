"""Habit Genome (V2).

Treats each recurring behaviour as a living entity with a lifecycle —
forming → growing → stable → declining → dormant → dead — tracked from its
weekly activity series. Also estimates whether a habit's active periods coincide
with the user's more productive weeks (outcome correlation). Measures, never
judges. Pure core is DB-free and unit-testable; `build(db)` is the adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

# Lifecycle stages a habit can occupy.
STAGES = ("forming", "growing", "stable", "declining", "dormant", "dead")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _conf(n: float, scale: float, base: float = 0.3, cap: float = 0.9) -> float:
    return round(min(cap, base + n / scale), 2)


def _pearson(xs: list[float], ys: list[float]) -> float:
    n = min(len(xs), len(ys))
    if n < 3:
        return 0.0
    mx, my = _mean(xs[:n]), _mean(ys[:n])
    num = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    dx = sum((xs[i] - mx) ** 2 for i in range(n)) ** 0.5
    dy = sum((ys[i] - my) ** 2 for i in range(n)) ** 0.5
    return round(num / (dx * dy), 3) if dx and dy else 0.0


@dataclass
class HabitGene:
    name: str
    stage: str
    strength: float          # 0..1 current vigor
    consistency: float       # 0..1 share of weeks active
    trend: float             # signed change in weekly rate
    age_weeks: int           # weeks since first observed
    last_active_weeks_ago: int
    outcome_correlation: float  # corr of this habit with productive weeks
    explanation: str
    evidence: dict = field(default_factory=dict)


def _stage(weekly: list[int]) -> tuple[str, int, int, float, float]:
    """Return (stage, age_weeks, last_active_weeks_ago, trend, consistency)."""
    total = len(weekly)
    active_idx = [i for i, v in enumerate(weekly) if v > 0]
    if not active_idx:
        return "dead", 0, total, 0.0, 0.0

    first, last = active_idx[0], active_idx[-1]
    age = total - first
    last_ago = total - 1 - last
    active_weeks = len(active_idx)
    consistency = round(active_weeks / total, 3)

    recent = _mean([float(v) for v in weekly[-4:]])
    earlier = _mean([float(v) for v in weekly[:-4]]) if total > 4 else 0.0
    trend = round(recent - earlier, 3)

    if last_ago >= 4:
        stage = "dead" if consistency <= 0.3 else "dormant"
    elif age <= 4:
        stage = "forming"
    elif trend > 0.5 and recent > earlier:
        stage = "growing"
    elif trend < -0.5:
        stage = "declining"
    else:
        stage = "stable"
    return stage, age, last_ago, trend, consistency


def classify_habit(name: str, weekly: list[int], productivity: list[int] | None = None) -> HabitGene:
    stage, age, last_ago, trend, consistency = _stage(weekly)
    recent = _mean([float(v) for v in weekly[-4:]])
    peak = max(weekly) if weekly else 0
    strength = round(min(1.0, 0.5 * (recent / peak if peak else 0) + 0.5 * consistency), 3)
    corr = _pearson([float(v) for v in weekly], [float(v) for v in (productivity or [])])

    verb = {
        "forming": "just emerged and is taking shape",
        "growing": "is gaining momentum",
        "stable": "is steady and well-established",
        "declining": "is losing momentum",
        "dormant": "has gone quiet recently",
        "dead": "appears to have faded out",
    }[stage]
    corr_note = (
        f" Its active weeks line up with your more productive weeks (r={corr})."
        if corr >= 0.4 else
        f" It tends to coincide with quieter weeks (r={corr})." if corr <= -0.4 else ""
    )
    return HabitGene(
        name=name,
        stage=stage,
        strength=strength,
        consistency=consistency,
        trend=trend,
        age_weeks=age,
        last_active_weeks_ago=last_ago,
        outcome_correlation=corr,
        explanation=(
            f"'{name}' {verb}: active in {round(consistency * 100)}% of tracked weeks, "
            f"last seen {last_ago} week(s) ago.{corr_note}"
        ),
        evidence={"weekly": weekly, "peak_week": peak},
    )


# --- DB adapter -------------------------------------------------------------
def build(db, weeks: int = 12, top_n: int = 12) -> dict:
    from datetime import timedelta
    from sqlalchemy import distinct, func, select
    from .models import Entity, Memory, MemoryEntity

    now = _now()
    bounds = [
        (now - timedelta(days=7 * (w + 1)), now - timedelta(days=7 * w))
        for w in range(weeks - 1, -1, -1)  # oldest first, recent last
    ]

    # Global weekly productivity (active days) for outcome correlation.
    productivity = [
        db.execute(
            select(func.count(distinct(func.date(Memory.ts)))).where(Memory.ts >= lo, Memory.ts < hi)
        ).scalar_one()
        for lo, hi in bounds
    ]

    # Candidate habits = explicit habit entities (e.g. tracked via ASCENSION)
    # plus the most-active skills + projects as a behavioural proxy.
    cand = db.execute(
        select(Entity.id, Entity.name)
        .join(MemoryEntity, MemoryEntity.entity_id == Entity.id)
        .join(Memory, Memory.id == MemoryEntity.memory_id)
        .where(Entity.type.in_(("skill", "project", "habit")))
        .group_by(Entity.id)
        .order_by(func.count(MemoryEntity.memory_id).desc())
        .limit(top_n)
    ).all()

    genes: list[HabitGene] = []
    for eid, name in cand:
        weekly = [
            db.execute(
                select(func.count(distinct(Memory.id)))
                .join(MemoryEntity, MemoryEntity.memory_id == Memory.id)
                .where(MemoryEntity.entity_id == eid, Memory.ts >= lo, Memory.ts < hi)
            ).scalar_one()
            for lo, hi in bounds
        ]
        if sum(weekly) == 0:
            continue
        genes.append(classify_habit(name, weekly, productivity))

    if not genes:
        return {"generated_at": now.isoformat(), "ready": False,
                "message": "No recurring behaviours with enough history yet."}

    order = {s: i for i, s in enumerate(STAGES)}
    genes.sort(key=lambda g: (order[g.stage], -g.strength))
    by_stage: dict[str, int] = {}
    for g in genes:
        by_stage[g.stage] = by_stage.get(g.stage, 0) + 1

    return {
        "generated_at": now.isoformat(),
        "ready": True,
        "weeks_observed": weeks,
        "confidence": _conf(sum(productivity), 60),
        "stage_counts": by_stage,
        "habits": [g.__dict__ for g in genes],
    }
