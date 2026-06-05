"""Layer 5 — the Cognitive Model (digital twin).

Estimates a structured, continuously-updating model of the person: how they
learn, how persistent they are, how they collaborate, where their attention and
knowledge concentrate. NOT a personality simulator — a structured, *evidence
-backed* representation. Every trait carries its score, confidence, the metrics
that produced it, and a plain-language explanation (explainability requirement).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import distinct, extract, func, select
from sqlalchemy.orm import Session

from .models import Entity, Memory, MemoryEntity
from .rhythm import best_window, rhythm_label, window_center


@dataclass
class Trait:
    name: str
    label: str            # human-readable summary of the value
    score: float          # 0..1 position on the trait's axis
    confidence: float
    explanation: str
    evidence: dict = field(default_factory=dict)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _conf(n: int, scale: int, base: float = 0.35, cap: float = 0.92) -> float:
    return round(min(cap, base + n / scale), 2)


def _norm(x: float, full: float) -> float:
    return round(min(1.0, x / full), 3)


def _project_rows(db: Session):
    return db.execute(
        select(
            Entity.id, Entity.name,
            func.count(distinct(MemoryEntity.memory_id)).label("n"),
            func.min(Memory.ts), func.max(Memory.ts),
        )
        .join(MemoryEntity, MemoryEntity.entity_id == Entity.id)
        .join(Memory, Memory.id == MemoryEntity.memory_id)
        .where(Entity.type == "project").group_by(Entity.id)
    ).all()


def _skill_rows(db: Session):
    return db.execute(
        select(
            Entity.name, Entity.weight,
            func.count(MemoryEntity.memory_id).label("n"),
            func.min(Memory.ts), func.max(Memory.ts),
        )
        .join(MemoryEntity, MemoryEntity.entity_id == Entity.id)
        .join(Memory, Memory.id == MemoryEntity.memory_id)
        .where(Entity.type == "skill").group_by(Entity.id)
        .order_by(Entity.weight.desc())
    ).all()


# --- traits -----------------------------------------------------------------
def _learning_style(db: Session) -> Trait | None:
    proj_mem = (
        select(distinct(MemoryEntity.memory_id))
        .join(Entity, Entity.id == MemoryEntity.entity_id)
        .where(Entity.type == "project").scalar_subquery()
    )
    total = db.execute(
        select(func.count(MemoryEntity.memory_id))
        .join(Entity, Entity.id == MemoryEntity.entity_id).where(Entity.type == "skill")
    ).scalar_one()
    if total < 5:
        return None
    in_proj = db.execute(
        select(func.count(MemoryEntity.memory_id))
        .join(Entity, Entity.id == MemoryEntity.entity_id)
        .where(Entity.type == "skill", MemoryEntity.memory_id.in_(proj_mem))
    ).scalar_one()
    frac = in_proj / total
    label = "Hands-on builder" if frac >= 0.6 else "Balanced learner" if frac >= 0.4 else "Reader / theorist"
    return Trait(
        "learning_style", label, round(frac, 3), _conf(total, 50),
        f"{round(frac*100)}% of your skill activity happens while building real projects "
        "rather than in isolation.",
        {"skill_links": total, "within_projects": in_proj},
    )


def _persistence(db: Session) -> Trait | None:
    rows = _project_rows(db)
    if len(rows) < 2:
        return None
    now = _now()
    spans = [(mx - mn).days for _, _, n, mn, mx in rows if n >= 2]
    if not spans:
        return None
    avg_span = sum(spans) / len(spans)
    neglected = sum(1 for _, _, _, _, mx in rows if (now - mx).days > 21)
    neglect_ratio = neglected / len(rows)
    score = round(_norm(avg_span, 90) * (1 - 0.6 * neglect_ratio), 3)
    label = "Highly persistent" if score >= 0.6 else "Moderately persistent" if score >= 0.3 else "Exploratory / starts many"
    return Trait(
        "persistence", label, score, _conf(len(rows), 12),
        f"Your projects span {round(avg_span)} days on average; "
        f"{neglected}/{len(rows)} have gone quiet for 3+ weeks.",
        {"avg_lifespan_days": round(avg_span), "neglected": neglected, "projects": len(rows)},
    )


def _collaboration(db: Session) -> Trait | None:
    rows = _project_rows(db)
    if len(rows) < 2:
        return None
    pe = MemoryEntity.__table__.alias("pe")
    qe = MemoryEntity.__table__.alias("qe")
    collab_ids = {
        r[0] for r in db.execute(
            select(distinct(pe.c.entity_id))
            .select_from(pe.join(qe, pe.c.memory_id == qe.c.memory_id))
            .join(Entity, Entity.id == pe.c.entity_id).where(Entity.type == "project")
            .where(qe.c.entity_id.in_(select(Entity.id).where(Entity.type == "person")))
        ).all()
    }
    frac = len(collab_ids) / len(rows)
    label = "Collaborative" if frac >= 0.5 else "Mixed" if frac >= 0.25 else "Independent"
    return Trait(
        "collaboration_preference", label, round(frac, 3), _conf(len(rows), 12),
        f"{len(collab_ids)} of {len(rows)} projects involve other people.",
        {"collaborative_projects": len(collab_ids), "projects": len(rows)},
    )


def _curiosity(db: Session) -> Trait | None:
    rows = _skill_rows(db)
    if len(rows) < 3:
        return None
    now = _now()
    new_recent = sum(1 for _, _, _, mn, _ in rows if (now - mn).days <= 60)
    breadth = _norm(len(rows), 15)
    novelty = _norm(new_recent, 5)
    score = round(0.6 * breadth + 0.4 * novelty, 3)
    label = "Highly curious" if score >= 0.6 else "Curious" if score >= 0.35 else "Focused / narrow"
    return Trait(
        "curiosity", label, score, _conf(len(rows), 20),
        f"You engage {len(rows)} distinct skills/topics, {new_recent} of them picked up "
        "in the last two months.",
        {"distinct_skills": len(rows), "new_last_60d": new_recent},
    )


def _focus(db: Session) -> Trait | None:
    rows = _project_rows(db)
    total = sum(n for _, _, n, _, _ in rows)
    if not rows or total < 5:
        return None
    top = max(n for _, _, n, _, _ in rows)
    share = top / total
    label = "Deep focuser" if share >= 0.5 else "Balanced" if share >= 0.3 else "Multitasker"
    return Trait(
        "focus_concentration", label, round(share, 3), _conf(total, 40),
        f"Your top project holds {round(share*100)}% of all project activity.",
        {"top_share": round(share, 3), "projects": len(rows)},
    )


def _attention_rhythm(db: Session) -> Trait | None:
    # Importance-weighted hour histogram, then the SAME best-window logic the
    # Pattern Engine uses — so the trait label and the peak_window pattern agree.
    rows = db.execute(
        select(extract("hour", Memory.ts).label("h"), func.sum(Memory.importance), func.count(Memory.id))
        .group_by("h")
    ).all()
    total = sum(int(c) for _, _, c in rows)
    if total < 8:
        return None
    weight = [0.0] * 24
    for h, imp, c in rows:
        weight[int(h)] = float(imp or 0.0)
    if sum(weight) == 0:  # fall back to counts if importance is all zero
        for h, _imp, c in rows:
            weight[int(h)] = float(c)

    start, end, share = best_window(weight, 4)
    center = window_center(start, 4)
    label = rhythm_label(center)
    return Trait(
        "attention_rhythm", label, round(center / 24, 3), _conf(total, 60),
        f"Your activity concentrates in the {start:02d}:00–{end:02d}:00 window (UTC).",
        {"peak_window": [start, end], "center_hour": center, "share": share},
    )


_TRAITS = [_learning_style, _persistence, _collaboration, _curiosity, _focus, _attention_rhythm]


def build(db: Session) -> dict:
    total_memories = db.execute(select(func.count(Memory.id))).scalar_one()
    by_type = dict(db.execute(
        select(Memory.memory_type, func.count(Memory.id)).group_by(Memory.memory_type)
    ).all())

    traits: list[Trait] = []
    for fn in _TRAITS:
        try:
            t = fn(db)
        except Exception:
            t = None
        if t:
            traits.append(t)

    knowledge = [
        {"skill": name, "weight": round(float(w), 2), "mentions": n,
         "last_seen": mx.isoformat() if mx else None}
        for name, w, n, _mn, mx in _skill_rows(db)[:12]
    ]

    summary = _summarize(traits)
    return {
        "generated_at": _now().isoformat(),
        "total_memories": total_memories,
        "memory_types": by_type,
        "traits": [t.__dict__ for t in traits],
        "knowledge_distribution": knowledge,
        "summary": summary,
        "maturity": _conf(total_memories, 200, base=0.1, cap=1.0),  # how settled the model is
    }


def _summarize(traits: list[Trait]) -> str:
    if not traits:
        return "Not enough data yet to model this person. Ingest more memories."
    pick = {t.name: t for t in traits}
    parts = []
    if "learning_style" in pick:
        parts.append(f"a {pick['learning_style'].label.lower()}")
    if "persistence" in pick:
        parts.append(pick["persistence"].label.lower())
    if "collaboration_preference" in pick:
        parts.append(pick["collaboration_preference"].label.lower())
    if "attention_rhythm" in pick:
        parts.append(f"working best as a {pick['attention_rhythm'].label.lower()}")
    return "This person is " + ", ".join(parts) + "." if parts else "Model forming."
