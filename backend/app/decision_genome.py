"""Decision Genome (V2).

PRL has no explicit "decision log", so significant decisions are *inferred* from
the data — chiefly the choice to start a project (its first memory). Each decision
is classified by its downstream trajectory (abandoned / stalled / sustained /
thriving), and the set is mined for the conditions under which the user's
decisions tend to follow through. Descriptive, never prescriptive.

Pure cores are DB-free and unit-testable; `build(db)` is the adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

OUTCOMES = ("abandoned", "stalled", "sustained", "thriving")
_GOOD = {"sustained", "thriving"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _conf(n: float, scale: float, base: float = 0.3, cap: float = 0.9) -> float:
    return round(min(cap, base + n / scale), 2)


@dataclass
class Decision:
    kind: str
    subject: str
    made_at: str
    outcome: str
    followthrough: float       # 0..1
    longevity_weeks: int
    collaborative: bool
    busy_start: bool
    explanation: str
    evidence: dict = field(default_factory=dict)


def classify_decision(weekly_after: list[int]) -> tuple[str, float, int]:
    """From the weekly activity following the decision return
    (outcome, followthrough, longevity_weeks)."""
    total = sum(weekly_after)
    active = [i for i, v in enumerate(weekly_after) if v > 0]
    n = len(weekly_after)
    if total <= 2 or not active:
        return "abandoned", round(min(1.0, total / 6), 3), 0
    last_ago = n - 1 - active[-1]
    active_weeks = len(active)
    longevity = active[-1] - active[0] + 1
    followthrough = round(min(1.0, 0.6 * (total / 12) + 0.4 * (active_weeks / n)), 3)
    if last_ago <= 2 and total >= 8 and active_weeks >= 4:
        outcome = "thriving"
    elif last_ago <= 4 and total >= 3:
        outcome = "sustained"
    else:
        outcome = "stalled"
    return outcome, followthrough, longevity


def _rate(items: list[bool]) -> float:
    return round(sum(items) / len(items), 3) if items else 0.0


@dataclass
class DecisionPattern:
    name: str
    observation: str
    success_with: float
    success_without: float
    lift: float
    sample: int
    confidence: float
    evidence: dict = field(default_factory=dict)


def decision_patterns(decisions: list[dict]) -> list[DecisionPattern]:
    """Mine follow-through rates by condition. Each `decision` dict needs
    keys: good(bool), collaborative(bool), busy_start(bool)."""
    if len(decisions) < 3:
        return []
    out: list[DecisionPattern] = []
    for key, label in (("collaborative", "involve other people"),
                       ("busy_start", "are started during a busy period")):
        with_ = [d["good"] for d in decisions if d.get(key)]
        without = [d["good"] for d in decisions if not d.get(key)]
        if len(with_) < 2 or len(without) < 2:
            continue
        sw, swo = _rate(with_), _rate(without)
        lift = round(sw - swo, 3)
        direction = "more" if lift > 0 else "less" if lift < 0 else "about as"
        out.append(DecisionPattern(
            name=key,
            observation=(
                f"Decisions that {label} follow through {abs(round(lift * 100))}% "
                f"{direction} often ({round(sw * 100)}% vs {round(swo * 100)}%)."
            ),
            success_with=sw, success_without=swo, lift=lift,
            sample=len(with_) + len(without),
            confidence=_conf(len(with_) + len(without), 12),
            evidence={"with": len(with_), "without": len(without)},
        ))
    out.sort(key=lambda p: abs(p.lift), reverse=True)
    return out


# --- DB adapter -------------------------------------------------------------
def build(db, max_weeks: int = 52) -> dict:
    from datetime import timedelta
    from sqlalchemy import distinct, func, select
    from .models import Entity, Memory, MemoryEntity

    now = _now()
    total_mem = db.execute(select(func.count(Memory.id))).scalar_one()
    span = db.execute(select(func.min(Memory.ts), func.max(Memory.ts))).first()
    if not total_mem or not span or not span[0]:
        return {"generated_at": now.isoformat(), "ready": False,
                "message": "Not enough history to infer decisions yet."}
    total_days = max((span[1] - span[0]).days, 1)
    biweekly_mean = total_mem / max(total_days / 14, 1)  # typical 2-week volume

    proj = db.execute(
        select(Entity.id, Entity.name, func.min(Memory.ts).label("start"))
        .join(MemoryEntity, MemoryEntity.entity_id == Entity.id)
        .join(Memory, Memory.id == MemoryEntity.memory_id)
        .where(Entity.type == "project").group_by(Entity.id)
    ).all()

    decisions: list[Decision] = []
    flat: list[dict] = []
    for eid, name, start in proj:
        weeks = min(max_weeks, max(1, (now - start).days // 7 + 1))
        weekly_after = [
            db.execute(
                select(func.count(distinct(Memory.id)))
                .join(MemoryEntity, MemoryEntity.memory_id == Memory.id)
                .where(MemoryEntity.entity_id == eid,
                       Memory.ts >= start + timedelta(days=7 * w),
                       Memory.ts < start + timedelta(days=7 * (w + 1)))
            ).scalar_one()
            for w in range(weeks)
        ]
        outcome, followthrough, longevity = classify_decision(weekly_after)

        collaborative = db.execute(
            select(func.count())
            .select_from(MemoryEntity)
            .join(Entity, Entity.id == MemoryEntity.entity_id)
            .where(Entity.type == "person",
                   MemoryEntity.memory_id.in_(
                       select(MemoryEntity.memory_id).where(MemoryEntity.entity_id == eid)))
        ).scalar_one() > 0

        around = db.execute(
            select(func.count(Memory.id)).where(
                Memory.ts >= start - timedelta(days=7), Memory.ts < start + timedelta(days=7))
        ).scalar_one()
        busy_start = around >= biweekly_mean

        good = outcome in _GOOD
        decisions.append(Decision(
            "start_project", name, start.isoformat(), outcome, followthrough, longevity,
            collaborative, busy_start,
            f"Starting '{name}' turned out {outcome}: {sum(weekly_after)} memories over "
            f"{longevity} active week(s){' with collaborators' if collaborative else ' solo'}.",
            {"total_after": sum(weekly_after), "around_start": around},
        ))
        flat.append({"good": good, "collaborative": collaborative, "busy_start": busy_start})

    if not decisions:
        return {"generated_at": now.isoformat(), "ready": False,
                "message": "No project-start decisions found to analyse."}

    order = {o: i for i, o in enumerate(OUTCOMES)}
    decisions.sort(key=lambda d: (-order[d.outcome], -d.followthrough))
    by_outcome: dict[str, int] = {}
    for d in decisions:
        by_outcome[d.outcome] = by_outcome.get(d.outcome, 0) + 1
    followthrough_rate = round(sum(1 for d in decisions if d.outcome in _GOOD) / len(decisions), 3)

    return {
        "generated_at": now.isoformat(),
        "ready": True,
        "note": "Decisions inferred from project starts. Describes follow-through, does not advise.",
        "confidence": _conf(len(decisions), 12),
        "decision_count": len(decisions),
        "followthrough_rate": followthrough_rate,
        "outcome_counts": by_outcome,
        "patterns": [p.__dict__ for p in decision_patterns(flat)],
        "decisions": [d.__dict__ for d in decisions],
    }
