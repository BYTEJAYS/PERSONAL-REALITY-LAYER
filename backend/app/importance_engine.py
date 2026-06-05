"""Importance Engine (Reality OS).

A universal, explainable importance score for every memory, blended from six
significances — emotional, relationship, financial, historical, frequency and
rarity. The score drives compression, retention, recall priority and aging, so it
is the foundation the Memory Economy and Forgetting engines build on.

Pure ``score_importance`` is DB-free and unit-testable; ``build(db)`` derives the
factors from each memory and the surrounding corpus. Read-only by default;
``apply=True`` writes the score back into ``meta`` non-destructively.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone

# Each significance is 0..1 (higher = more important). Weights sum to 1.
WEIGHTS = {
    "emotional": 0.25,
    "relationship": 0.20,
    "historical": 0.20,
    "financial": 0.15,
    "rarity": 0.15,
    "frequency": 0.05,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ImportanceFactors:
    emotional: float = 0.0      # strength of feeling attached
    relationship: float = 0.0   # how many / how close the people involved
    financial: float = 0.0      # monetary impact
    historical: float = 0.0     # will it still matter in 10 years
    frequency: float = 0.0      # significance from how routine it is (rare→high)
    rarity: float = 0.0         # uniqueness of the event

    def clamp(self) -> "ImportanceFactors":
        for f in WEIGHTS:
            setattr(self, f, max(0.0, min(1.0, getattr(self, f))))
        return self


def label_for(score: float) -> str:
    if score >= 0.75:
        return "Very High"
    if score >= 0.5:
        return "High"
    if score >= 0.25:
        return "Medium"
    return "Low"


def score_importance(factors: ImportanceFactors, weights: dict | None = None) -> dict:
    w = weights or WEIGHTS
    factors.clamp()
    contributions = {k: round(getattr(factors, k) * w[k], 4) for k in w}
    score = round(sum(contributions.values()), 4)
    # Name the one or two factors that drove the score.
    drivers = [k for k, _ in sorted(contributions.items(), key=lambda kv: -kv[1])[:2]
               if contributions[k] > 0]
    return {
        "score": score,
        "label": label_for(score),
        "breakdown": contributions,
        "drivers": drivers,
    }


# --- factor derivation (pure, given corpus stats) ---------------------------
@dataclass
class CorpusStats:
    type_freq: dict           # memory_type -> share 0..1
    max_people: int           # most people on any single memory
    total: int


def derive_factors(memory: dict, stats: CorpusStats,
                   emotion_valence) -> ImportanceFactors:
    """Map one memory (+ corpus context) to its six significances. `emotion_valence`
    is a callable str->float in [-1,1]; magnitude = emotional intensity."""
    emo = abs(emotion_valence(memory.get("emotion") or ""))
    people = memory.get("people_count", 0)
    relationship = min(1.0, people / max(1, stats.max_people)) if stats.max_people else 0.0
    financial = 1.0 if memory.get("has_finance") else 0.0
    mtype = memory.get("memory_type", "episodic")
    # Historical weight: goals/social/health-bearing memories tend to age well.
    historical = {"goal": 0.9, "social": 0.7, "knowledge": 0.6,
                  "episodic": 0.4}.get(mtype, 0.4)
    if memory.get("has_health"):
        historical = max(historical, 0.8)
    share = stats.type_freq.get(mtype, 0.0)
    frequency = 1.0 - min(1.0, share)            # common type → low per-item significance
    rarity = 1.0 if memory.get("is_unique", True) else 0.3
    return ImportanceFactors(emo, relationship, financial, historical,
                             frequency, rarity).clamp()


# --- DB adapter -------------------------------------------------------------
def build(db, apply: bool = False) -> dict:
    from sqlalchemy import select
    from .models import Entity, Memory, MemoryEntity
    from .emotional_cortex import valence

    rows = db.execute(
        select(Memory.id, Memory.memory_type, Memory.emotion, Memory.meta)
    ).all()
    if not rows:
        return {"ready": False, "message": "No memories to score yet."}

    # People per memory + corpus stats.
    people_rows = db.execute(
        select(MemoryEntity.memory_id)
        .join(Entity, Entity.id == MemoryEntity.entity_id)
        .where(Entity.type == "person")
    ).all()
    people_count: Counter = Counter(str(mid) for (mid,) in people_rows)
    type_counter: Counter = Counter(mt or "episodic" for _, mt, _, _ in rows)
    total = len(rows)
    stats = CorpusStats(
        type_freq={k: v / total for k, v in type_counter.items()},
        max_people=max(people_count.values()) if people_count else 0,
        total=total,
    )

    scored = []
    dist = Counter()
    for mid, mtype, emotion, meta in rows:
        meta = meta or {}
        mem = {
            "memory_type": mtype,
            "emotion": emotion,
            "people_count": people_count.get(str(mid), 0),
            "has_finance": bool(meta.get("finance")),
            "has_health": bool(meta.get("health")),
            "is_unique": "compressed_into" not in meta and "redundant_of" not in meta,
        }
        res = score_importance(derive_factors(mem, stats, valence))
        dist[res["label"]] += 1
        scored.append((mid, res))
        if apply:
            m = db.get(Memory, mid)
            if m is not None:
                m.meta = {**meta, "importance_v2": res}
    if apply:
        db.commit()

    scored.sort(key=lambda s: -s[1]["score"])
    return {
        "ready": True,
        "generated_at": _now().isoformat(),
        "applied": apply,
        "scored": total,
        "distribution": dict(dist),
        "weights": WEIGHTS,
        "top": [{"memory_id": str(mid), **res} for mid, res in scored[:20]],
    }
