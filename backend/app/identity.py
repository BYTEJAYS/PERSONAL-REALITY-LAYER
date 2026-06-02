"""Identity Model — claim vs. observed behaviour (V2).

Compares what the user *claims* to want (stated goals) against what they
*actually pursue* (where activity goes), surfacing alignment and contradictions.
It measures, it never judges — the language stays neutral and evidence-backed.
Pure scoring core is DB-free; `assess(db)` supplies real goal/activity counts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _conf(n: float, scale: float, base: float = 0.3, cap: float = 0.9) -> float:
    return round(min(cap, base + n / scale), 2)


@dataclass
class GoalAlignment:
    goal: str
    claim_strength: float   # 0..1 how strongly it's stated/prioritised
    pursuit_share: float    # 0..1 fraction of recent activity touching it
    alignment: str          # strong | partial | weak
    contradiction: bool     # claimed priority but little observed pursuit
    explanation: str
    evidence: dict = field(default_factory=dict)


def score_goal(name: str, claim_strength: float, recent_activity: int, total_recent: int) -> GoalAlignment:
    share = round(recent_activity / total_recent, 3) if total_recent else 0.0
    if share >= 0.25:
        alignment = "strong"
    elif share >= 0.08:
        alignment = "partial"
    else:
        alignment = "weak"
    contradiction = claim_strength >= 0.6 and share < 0.08
    explanation = (
        f"Stated priority ~{round(claim_strength * 100)}%, but it accounts for "
        f"{round(share * 100)}% of your recent activity "
        f"({recent_activity}/{total_recent} memories) — {alignment} alignment"
        + (". Claimed as important yet rarely pursued." if contradiction else ".")
    )
    return GoalAlignment(
        goal=name,
        claim_strength=round(claim_strength, 3),
        pursuit_share=share,
        alignment=alignment,
        contradiction=contradiction,
        explanation=explanation,
        evidence={"recent_activity": recent_activity, "total_recent": total_recent},
    )


# --- DB adapter -------------------------------------------------------------
def assess(db, window_days: int = 90) -> dict:
    from datetime import timedelta
    from sqlalchemy import distinct, func, select
    from .models import Entity, Memory, MemoryEntity

    now = _now()
    since = now - timedelta(days=window_days)

    total_recent = db.execute(
        select(func.count(Memory.id)).where(Memory.ts >= since)
    ).scalar_one()

    goal_rows = db.execute(
        select(
            Entity.name,
            Entity.weight,
            func.count(distinct(MemoryEntity.memory_id)).filter(Memory.ts >= since).label("recent"),
        )
        .join(MemoryEntity, MemoryEntity.entity_id == Entity.id)
        .join(Memory, Memory.id == MemoryEntity.memory_id)
        .where(Entity.type == "goal")
        .group_by(Entity.id)
        .order_by(Entity.weight.desc())
    ).all()

    if not goal_rows or total_recent == 0:
        return {
            "generated_at": now.isoformat(),
            "ready": False,
            "message": "No stated goals (goal entities) or no recent activity to compare against.",
        }

    max_w = max((float(w) for _, w, _ in goal_rows), default=1.0) or 1.0
    alignments = [
        score_goal(name, min(1.0, float(w) / max_w), int(recent or 0), total_recent)
        for name, w, recent in goal_rows
    ]

    contradictions = [a.goal for a in alignments if a.contradiction]
    return {
        "generated_at": now.isoformat(),
        "ready": True,
        "window_days": window_days,
        "confidence": _conf(total_recent, 80),
        "note": "Measures alignment between stated goals and observed behaviour. Descriptive, not prescriptive.",
        "alignments": [a.__dict__ for a in alignments],
        "contradictions": contradictions,
    }
