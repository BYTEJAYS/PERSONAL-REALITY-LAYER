"""Self-Evolution Engine (Reality OS) — #10, PARTIAL → BUILT.

No two PRLs should evolve the same way. This engine personalises how importance is
judged: it watches which memories the user actually treats as important and
nudges the Importance Engine's factor weights toward that revealed preference, so
over time PRL weighs reality the way *this* person does.

Pure ``adapt_weights`` is a small from-scratch gradient fit, DB-free and
unit-testable; ``build(db)`` gathers the feedback examples and adapts.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .importance_engine import WEIGHTS as BASE_WEIGHTS

FACTORS = tuple(BASE_WEIGHTS.keys())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalise(w: dict) -> dict:
    w = {k: max(0.0, v) for k, v in w.items()}
    s = sum(w.values()) or 1.0
    return {k: round(v / s, 4) for k, v in w.items()}


def adapt_weights(examples: list[tuple[dict, float]], base: dict | None = None,
                  lr: float = 0.3, epochs: int = 200) -> dict:
    """Fit factor weights to revealed preference.

    `examples` = [(factors_dict, label 0..1)] where label is how important the user
    treated that memory. Gradient descent on squared error of a weighted-sum
    predictor, blended back toward `base` by how much data we have (thin data →
    trust the priors). Returns normalised weights summing to 1.
    """
    base = base or dict(BASE_WEIGHTS)
    if not examples:
        return _normalise(base)

    w = dict(base)
    for _ in range(epochs):
        for factors, label in examples:
            pred = sum(w.get(f, 0.0) * factors.get(f, 0.0) for f in FACTORS)
            err = label - pred
            for f in FACTORS:
                w[f] = w.get(f, 0.0) + lr * err * factors.get(f, 0.0)
            w = {k: max(0.0, v) for k, v in w.items()}

    learned = _normalise(w)
    # Blend learned vs prior by confidence in the data volume.
    strength = min(0.8, len(examples) / 25.0)
    blended = {f: (1 - strength) * base.get(f, 0.0) + strength * learned.get(f, 0.0)
               for f in FACTORS}
    return _normalise(blended)


def learned_priorities(weights: dict, top: int = 3) -> list[str]:
    """Readable account of what this user weighs most."""
    return [f for f, _ in sorted(weights.items(), key=lambda kv: -kv[1])[:top]]


def weight_shift(base: dict, evolved: dict) -> dict:
    """How each factor's weight moved from the default — the evolution itself."""
    return {f: round(evolved.get(f, 0.0) - base.get(f, 0.0), 4) for f in FACTORS}


# --- DB adapter -------------------------------------------------------------
def build(db) -> dict:
    from sqlalchemy import select
    from collections import Counter
    from .models import Entity, Memory, MemoryEntity
    from .importance_engine import CorpusStats, derive_factors
    from .emotional_cortex import valence

    rows = db.execute(
        select(Memory.id, Memory.memory_type, Memory.emotion, Memory.importance, Memory.meta)
    ).all()
    if not rows:
        return {"ready": False, "message": "No feedback to learn from yet."}

    people_rows = db.execute(
        select(MemoryEntity.memory_id).join(Entity, Entity.id == MemoryEntity.entity_id)
        .where(Entity.type == "person")).all()
    people_count = Counter(str(mid) for (mid,) in people_rows)
    type_counter = Counter(mt or "episodic" for _, mt, _, _, _ in rows)
    total = len(rows)
    stats = CorpusStats({k: v / total for k, v in type_counter.items()},
                        max(people_count.values()) if people_count else 0, total)

    # Label = explicit user feedback if present, else the stored importance as a
    # proxy for revealed preference.
    examples = []
    for mid, mtype, emotion, imp, meta in rows:
        meta = meta or {}
        mem = {"memory_type": mtype, "emotion": emotion,
               "people_count": people_count.get(str(mid), 0),
               "has_finance": bool(meta.get("finance")),
               "has_health": bool(meta.get("health")),
               "is_unique": "compressed_into" not in meta}
        factors = derive_factors(mem, stats, valence).__dict__
        label = meta.get("feedback_important")
        if label is None:
            label = imp if imp is not None else 0.5
        examples.append((factors, float(label)))

    evolved = adapt_weights(examples)
    return {
        "ready": True,
        "generated_at": _now().isoformat(),
        "examples": len(examples),
        "base_weights": dict(BASE_WEIGHTS),
        "evolved_weights": evolved,
        "shift": weight_shift(dict(BASE_WEIGHTS), evolved),
        "priorities": learned_priorities(evolved),
    }
