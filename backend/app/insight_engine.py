"""Insight Engine.

Mines the memory store for observations about the user's life and habits. Every
insight is computed from real aggregates and carries its evidence (the numbers
that produced it, and example memories). Generators that lack enough data return
nothing — the engine never fabricates a pattern it can't support.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import distinct, extract, func, select
from sqlalchemy.orm import Session

from .models import Entity, Memory, MemoryEntity

WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


@dataclass
class Insight:
    key: str
    category: str           # rhythm | focus | habit | learning | momentum
    observation: str        # the headline
    detail: str             # the supporting explanation
    confidence: float       # 0..1, scales with sample size
    evidence: dict = field(default_factory=dict)
    citations: list[dict] = field(default_factory=list)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _conf(sample: int, scale: int, base: float = 0.4, cap: float = 0.95) -> float:
    return round(min(cap, base + sample / scale), 2)


def _cite(m: Memory) -> dict:
    return {"id": str(m.id), "ts": m.ts.isoformat(), "title": m.title, "source": m.source}


# --- generators -------------------------------------------------------------
def _peak_hour(db: Session) -> Insight | None:
    rows = db.execute(
        select(extract("hour", Memory.ts).label("h"),
               func.count(Memory.id), func.coalesce(func.sum(Memory.importance), 0.0))
        .group_by("h")
    ).all()
    total = sum(c for _, c, _ in rows)
    if total < 8:
        return None
    rows.sort(key=lambda r: r[2], reverse=True)
    h = int(rows[0][0])
    label = ("the early hours" if h < 6 else "the morning" if h < 12
             else "the afternoon" if h < 17 else "the evening" if h < 21 else "late at night")
    share = round(100 * rows[0][1] / total)
    return Insight(
        key="peak_hour", category="rhythm",
        observation=f"You're most active in {label} — around {h:02d}:00.",
        detail=f"{share}% of your most important activity clusters there.",
        confidence=_conf(total, 60),
        evidence={"by_hour": sorted([[int(h_), c] for h_, c, _ in rows]), "timezone": "UTC"},
    )


def _busiest_weekday(db: Session) -> Insight | None:
    rows = db.execute(
        select(extract("dow", Memory.ts).label("d"), func.count(Memory.id)).group_by("d")
    ).all()
    total = sum(c for _, c in rows)
    if total < 10:
        return None
    rows.sort(key=lambda r: r[1], reverse=True)
    day = WEEKDAYS[int(rows[0][0])]
    return Insight(
        key="busiest_weekday", category="rhythm",
        observation=f"{day} is your most productive day.",
        detail=f"It accounts for the largest share of your recorded activity.",
        confidence=_conf(total, 80),
        evidence={"by_weekday": [[WEEKDAYS[int(d)], c] for d, c in rows]},
    )


def _top_focus(db: Session) -> Insight | None:
    rows = db.execute(
        select(Entity.id, Entity.name, func.count(MemoryEntity.memory_id).label("n"))
        .join(MemoryEntity, MemoryEntity.entity_id == Entity.id)
        .where(Entity.type == "project")
        .group_by(Entity.id).order_by(func.count(MemoryEntity.memory_id).desc())
    ).all()
    total = sum(n for _, _, n in rows)
    if not rows or total < 5:
        return None
    eid, name, n = rows[0]
    share = round(100 * n / total)
    recent = db.execute(
        select(Memory).join(MemoryEntity, MemoryEntity.memory_id == Memory.id)
        .where(MemoryEntity.entity_id == eid).order_by(Memory.ts.desc()).limit(3)
    ).scalars().all()
    return Insight(
        key="top_focus", category="focus",
        observation=f"{name} is your primary focus.",
        detail=f"It represents {share}% of all your project activity ({n} memories).",
        confidence=_conf(total, 40),
        evidence={"ranking": [[nm, c] for _, nm, c in rows[:6]]},
        citations=[_cite(m) for m in recent],
    )


def _neglected(db: Session) -> Insight | None:
    cutoff = _now() - timedelta(days=21)
    rows = db.execute(
        select(Entity.name, func.max(Memory.ts))
        .join(MemoryEntity, MemoryEntity.entity_id == Entity.id)
        .join(Memory, Memory.id == MemoryEntity.memory_id)
        .where(Entity.type == "project")
        .group_by(Entity.id).having(func.max(Memory.ts) < cutoff)
        .order_by(func.max(Memory.ts).asc())
    ).all()
    if not rows:
        return None
    names = [n for n, _ in rows[:4]]
    return Insight(
        key="neglected", category="habit",
        observation="Some projects have gone quiet.",
        detail="No activity in over three weeks on: " + ", ".join(names) + ".",
        confidence=0.7,
        evidence={"neglected": [[n, ts.isoformat()] for n, ts in rows]},
    )


def _learning_in_projects(db: Session) -> Insight | None:
    # Memories that involve a project.
    proj_mem = (
        select(distinct(MemoryEntity.memory_id))
        .join(Entity, Entity.id == MemoryEntity.entity_id)
        .where(Entity.type == "project").scalar_subquery()
    )
    skill_total = db.execute(
        select(func.count(MemoryEntity.memory_id))
        .join(Entity, Entity.id == MemoryEntity.entity_id)
        .where(Entity.type == "skill")
    ).scalar_one()
    if skill_total < 6:
        return None
    skill_in_proj = db.execute(
        select(func.count(MemoryEntity.memory_id))
        .join(Entity, Entity.id == MemoryEntity.entity_id)
        .where(Entity.type == "skill", MemoryEntity.memory_id.in_(proj_mem))
    ).scalar_one()
    frac = skill_in_proj / skill_total
    if frac < 0.45:
        return None
    return Insight(
        key="learning_in_projects", category="learning",
        observation="Most of your learning happens inside project work.",
        detail=f"{round(frac * 100)}% of your skill activity co-occurs with a project, "
               "rather than in isolation.",
        confidence=_conf(skill_total, 50),
        evidence={"skill_links": skill_total, "within_projects": skill_in_proj},
    )


def _collaboration(db: Session) -> Insight | None:
    # Per-project memory counts.
    counts = dict(
        db.execute(
            select(Entity.id, func.count(distinct(MemoryEntity.memory_id)))
            .join(MemoryEntity, MemoryEntity.entity_id == Entity.id)
            .where(Entity.type == "project").group_by(Entity.id)
        ).all()
    )
    if len(counts) < 3:
        return None
    # Projects that share a memory with a person → collaborative.
    pe = MemoryEntity.__table__.alias("pe")
    qe = MemoryEntity.__table__.alias("qe")
    collab_ids = {
        r[0] for r in db.execute(
            select(distinct(pe.c.entity_id))
            .select_from(pe.join(qe, pe.c.memory_id == qe.c.memory_id))
            .join(Entity, Entity.id == pe.c.entity_id)
            .where(Entity.type == "project")
            .where(qe.c.entity_id.in_(select(Entity.id).where(Entity.type == "person")))
        ).all()
    }
    collab = [c for eid, c in counts.items() if eid in collab_ids]
    solo = [c for eid, c in counts.items() if eid not in collab_ids]
    if not collab or not solo:
        return None
    avg_c = sum(collab) / len(collab)
    avg_s = sum(solo) / len(solo)
    if avg_c <= avg_s * 1.25:
        return None
    ratio = round(avg_c / max(avg_s, 0.5), 1)
    return Insight(
        key="collaboration", category="habit",
        observation="Your collaborative projects get more done.",
        detail=f"Projects involving other people average {ratio}× more activity "
               f"than solo ones.",
        confidence=_conf(len(counts), 20),
        evidence={"avg_collaborative": round(avg_c, 1), "avg_solo": round(avg_s, 1),
                  "collaborative_projects": len(collab), "solo_projects": len(solo)},
    )


def _momentum(db: Session) -> Insight | None:
    now = _now()
    recent = db.execute(
        select(func.count(Memory.id)).where(Memory.ts >= now - timedelta(days=30))
    ).scalar_one()
    prior = db.execute(
        select(func.count(Memory.id))
        .where(Memory.ts >= now - timedelta(days=60), Memory.ts < now - timedelta(days=30))
    ).scalar_one()
    if recent + prior < 8:
        return None
    if prior == 0:
        return Insight(
            key="momentum", category="momentum",
            observation="You're ramping up.",
            detail=f"{recent} memories in the last 30 days, after a quiet prior month.",
            confidence=0.6, evidence={"recent_30d": recent, "prior_30d": prior},
        )
    change = (recent - prior) / prior
    direction = "accelerating" if change > 0.15 else "slowing down" if change < -0.15 else "steady"
    return Insight(
        key="momentum", category="momentum",
        observation=f"Your activity is {direction}.",
        detail=f"{recent} memories in the last 30 days vs {prior} the month before "
               f"({'+' if change >= 0 else ''}{round(change * 100)}%).",
        confidence=_conf(recent + prior, 60),
        evidence={"recent_30d": recent, "prior_30d": prior, "change_pct": round(change * 100)},
    )


_GENERATORS = [
    _peak_hour, _busiest_weekday, _top_focus, _neglected,
    _learning_in_projects, _collaboration, _momentum,
]


def generate(db: Session) -> list[Insight]:
    out: list[Insight] = []
    for gen in _GENERATORS:
        try:
            ins = gen(db)
        except Exception:  # one bad generator shouldn't sink the rest
            continue
        if ins is not None:
            out.append(ins)
    out.sort(key=lambda i: i.confidence, reverse=True)
    return out
