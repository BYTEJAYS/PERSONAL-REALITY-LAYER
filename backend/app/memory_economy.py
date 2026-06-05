"""Memory Economy System (Reality OS).

Storage is finite, so every memory earns its keep. Memory Value blends how much
it matters (importance), how much we trust it (confidence) and who it connects to
(relationship weight), divided by what it costs to store. High-value memories stay
detailed; low-value ones get aggressively compressed or dropped — this is the
economic policy the Forgetting engine enforces.

Pure ``memory_value`` / ``compression_policy`` are DB-free and unit-testable;
``build(db)`` combines the Importance and Confidence engines over the store.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone

POLICIES = ("keep_full", "compress", "aggressive_compress", "drop")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def memory_value(importance: float, confidence: float,
                 relationship_weight: float, storage_cost: float) -> float:
    """Value = importance × confidence × relationship / storage_cost.

    `storage_cost` is normalised 0..1 (1 = the largest memory); it is floored so a
    tiny memory cannot divide value to infinity."""
    rel = 0.5 + 0.5 * _clamp(relationship_weight)   # relationships never fully zero out value
    cost = max(storage_cost, 0.1)
    return round(_clamp(importance) * _clamp(confidence) * rel / cost, 4)


def compression_policy(value: float) -> str:
    if value >= 2.0:
        return "keep_full"
    if value >= 0.8:
        return "compress"
    if value >= 0.3:
        return "aggressive_compress"
    return "drop"


@dataclass
class MemoryEcon:
    memory_id: str
    importance: float
    confidence: float
    relationship_weight: float
    storage_cost: float

    def evaluate(self) -> dict:
        v = memory_value(self.importance, self.confidence,
                         self.relationship_weight, self.storage_cost)
        return {"memory_id": self.memory_id, "value": v, "policy": compression_policy(v)}


# --- DB adapter -------------------------------------------------------------
def build(db) -> dict:
    from sqlalchemy import select
    from .models import Entity, Memory, MemoryEntity
    from . import importance_engine
    from .confidence_engine import Evidence, score_confidence

    rows = db.execute(
        select(Memory.id, Memory.content, Memory.source, Memory.meta).limit(5000)
    ).all()
    if not rows:
        return {"ready": False, "message": "No memories to value yet."}

    # Importance per memory (reuse the engine; falls back to 0.5 if absent).
    imp_report = importance_engine.build(db)
    imp_by_id = {t["memory_id"]: t["score"] for t in imp_report.get("top", [])}

    # Relationship weight per memory = summed entity weight of linked entities.
    rel_rows = db.execute(
        select(MemoryEntity.memory_id, Entity.weight).join(
            Entity, Entity.id == MemoryEntity.entity_id)
    ).all()
    rel_by_id: Counter = Counter()
    for mid, w in rel_rows:
        rel_by_id[str(mid)] += (w or 0.0)
    max_rel = max(rel_by_id.values()) if rel_by_id else 1.0

    max_len = max((len(c or "") for _, c, _, _ in rows), default=1) or 1

    dist = Counter()
    evaluated = []
    for mid, content, source, meta in rows:
        meta = meta or {}
        imp = imp_by_id.get(str(mid), 0.5)
        conf = score_confidence(Evidence(sources=[source], timestamp_reliable=True))["confidence"]
        rel = rel_by_id.get(str(mid), 0.0) / max_rel if max_rel else 0.0
        cost = len(content or "") / max_len
        econ = MemoryEcon(str(mid), imp, conf, rel, cost).evaluate()
        dist[econ["policy"]] += 1
        evaluated.append(econ)

    evaluated.sort(key=lambda e: -e["value"])
    return {
        "ready": True,
        "generated_at": _now().isoformat(),
        "valued": len(evaluated),
        "policy_distribution": dict(dist),
        "most_valuable": evaluated[:15],
        "least_valuable": evaluated[-15:],
    }
