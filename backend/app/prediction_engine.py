"""Prediction Engine.

Probabilistic forecasts derived from behavioural evidence — burnout risk,
project-completion likelihood, habit stability, knowledge decay. Predictions are
ALWAYS expressed as probabilities with confidence and supporting evidence, never
as certainties (per the spec). Each carries a plain-language explanation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from .models import Entity, Memory, MemoryEntity


@dataclass
class Prediction:
    kind: str
    target: str
    probability: float       # 0..1
    confidence: float        # how much data backs it
    horizon: str
    explanation: str
    evidence: dict = field(default_factory=dict)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _conf(n: int, scale: int, base: float = 0.3, cap: float = 0.9) -> float:
    return round(min(cap, base + n / scale), 2)


def _clamp(x: float) -> float:
    return round(max(0.02, min(0.98, x)), 3)


def _counts(db: Session, days_from: int, days_to: int) -> int:
    now = _now()
    return db.execute(
        select(func.count(Memory.id)).where(
            Memory.ts >= now - timedelta(days=days_from),
            Memory.ts < now - timedelta(days=days_to),
        )
    ).scalar_one()


def _burnout(db: Session) -> Prediction | None:
    recent = _counts(db, 7, 0)
    base = _counts(db, 28, 7) / 3 if _counts(db, 28, 7) else 0  # avg weekly over prior 3 weeks
    total = recent + _counts(db, 28, 7)
    if total < 8:
        return None
    # Social contact in the last 2 weeks (isolation raises risk).
    social = db.execute(
        select(func.count(distinct(Memory.id)))
        .join(MemoryEntity, MemoryEntity.memory_id == Memory.id)
        .join(Entity, Entity.id == MemoryEntity.entity_id)
        .where(Entity.type == "person", Memory.ts >= _now() - timedelta(days=14))
    ).scalar_one()

    overwork = max(0.0, (recent - base) / max(base, 1)) if base else (0.4 if recent > 8 else 0.0)
    isolation = 1.0 if social == 0 else 0.4 if social <= 2 else 0.0
    risk = _clamp(0.25 + 0.45 * min(overwork, 1.5) / 1.5 + 0.3 * isolation)
    return Prediction(
        "burnout_risk", "you", risk, _conf(total, 40), "next 1–2 weeks",
        f"Recent weekly activity is {recent} vs a ~{round(base,1)} baseline; "
        f"{'no' if social == 0 else social} social interactions in the last 14 days.",
        {"recent_7d": recent, "weekly_baseline": round(base, 1), "social_14d": social},
    )


def _project_completion(db: Session) -> list[Prediction]:
    rows = db.execute(
        select(
            Entity.name,
            func.count(distinct(MemoryEntity.memory_id)).label("n"),
            func.min(Memory.ts), func.max(Memory.ts),
        )
        .join(MemoryEntity, MemoryEntity.entity_id == Entity.id)
        .join(Memory, Memory.id == MemoryEntity.memory_id)
        .where(Entity.type == "project").group_by(Entity.id)
    ).all()
    now = _now()
    out: list[Prediction] = []
    for name, n, mn, mx in rows:
        if n < 2:
            continue
        days_idle = (now - mx).days
        span = max((mx - mn).days, 1)
        recency = max(0.0, 1 - days_idle / 30)          # fresher → more likely to finish
        momentum = min(1.0, n / max(span / 7, 1) / 3)    # memories per week, capped
        prob = _clamp(0.2 + 0.5 * recency + 0.3 * momentum)
        out.append(Prediction(
            "project_completion", name, prob, _conf(n, 15), "next 30 days",
            f"{n} memories over {span} days; last touched {days_idle} days ago.",
            {"memories": n, "days_idle": days_idle, "span_days": span},
        ))
    out.sort(key=lambda p: p.probability, reverse=True)
    return out[:6]


def _habit_stability(db: Session) -> Prediction | None:
    # Active-day consistency over the last 6 weeks.
    now = _now()
    weeks = []
    for w in range(6):
        c = db.execute(
            select(func.count(distinct(func.date(Memory.ts))))
            .where(Memory.ts >= now - timedelta(days=7 * (w + 1)),
                   Memory.ts < now - timedelta(days=7 * w))
        ).scalar_one()
        weeks.append(c)
    if sum(weeks) < 6:
        return None
    mean = sum(weeks) / len(weeks)
    var = sum((x - mean) ** 2 for x in weeks) / len(weeks)
    cv = (var ** 0.5) / mean if mean else 1
    stability = _clamp(1 - min(cv, 1))
    return Prediction(
        "habit_stability", "daily routine", stability, _conf(sum(weeks), 30), "ongoing",
        f"You were active on ~{round(mean,1)} days/week with "
        f"{'low' if cv < 0.4 else 'high'} week-to-week variance.",
        {"active_days_per_week": [int(x) for x in weeks], "mean": round(mean, 1)},
    )


def _knowledge_decay(db: Session) -> list[Prediction]:
    rows = db.execute(
        select(Entity.name, Entity.weight, func.max(Memory.ts))
        .join(MemoryEntity, MemoryEntity.entity_id == Entity.id)
        .join(Memory, Memory.id == MemoryEntity.memory_id)
        .where(Entity.type == "skill").group_by(Entity.id)
        .order_by(Entity.weight.desc())
    ).all()
    now = _now()
    out: list[Prediction] = []
    for name, w, mx in rows:
        idle = (now - mx).days
        if idle < 30:
            continue
        decay = _clamp(min(0.95, idle / 180))  # unreinforced → rising decay risk
        out.append(Prediction(
            "knowledge_decay", name, decay, _conf(int(w * 10), 30), "ongoing",
            f"Not reinforced in {idle} days — retention likely fading without practice.",
            {"days_since_use": idle, "weight": round(float(w), 2)},
        ))
    out.sort(key=lambda p: p.probability, reverse=True)
    return out[:6]


def forecast(db: Session) -> dict:
    preds: list[Prediction] = []
    b = _burnout(db)
    if b:
        preds.append(b)
    h = _habit_stability(db)
    if h:
        preds.append(h)
    preds += _project_completion(db)
    preds += _knowledge_decay(db)
    return {
        "generated_at": _now().isoformat(),
        "disclaimer": "Probabilistic estimates from behavioural evidence — not certainties.",
        "count": len(preds),
        "predictions": [p.__dict__ for p in preds],
    }
