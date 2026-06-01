"""Brain-state aggregation.

Turns the canonical memory/entity store into the live cognitive state the
Cortex particle-brain renders. Region sizes are NOT decorative — they are real
counts. As ingestion grows the store, the brain visibly grows with it, which is
the whole product thesis.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import REGION_FOR_ENTITY, Entity, Memory, MemoryEntity

REGIONS = ("memory", "knowledge", "project", "goal", "social")

# Entity types that feed each region (memory region is also fed by raw memories).
_TYPES_FOR_REGION = {
    "memory": ["place"],
    "knowledge": ["skill"],
    "project": ["project"],
    "goal": ["goal"],
    "social": ["person"],
}


def brain_state(db: Session) -> dict:
    """Region intensities + headline counts for the cortex frontend."""
    total_memories = db.execute(select(func.count(Memory.id))).scalar_one()

    # weight + count per entity type
    rows = db.execute(
        select(Entity.type, func.count(Entity.id), func.coalesce(func.sum(Entity.weight), 0.0))
        .group_by(Entity.type)
    ).all()
    by_type = {t: {"count": c, "weight": float(w)} for t, c, w in rows}

    regions = []
    for region in REGIONS:
        count = 0
        weight = 0.0
        for t in _TYPES_FOR_REGION[region]:
            count += by_type.get(t, {}).get("count", 0)
            weight += by_type.get(t, {}).get("weight", 0.0)
        if region == "memory":
            # The memory region also reflects the raw volume of experiences.
            count += total_memories
            weight += total_memories * 0.5
        regions.append({"region": region, "count": count, "weight": round(weight, 3)})

    max_weight = max((r["weight"] for r in regions), default=0.0) or 1.0
    for r in regions:
        # Particle budget per region, normalised to a 0..1 intensity.
        r["intensity"] = round(r["weight"] / max_weight, 4)

    return {
        "total_memories": total_memories,
        "total_entities": sum(v["count"] for v in by_type.values()),
        "regions": regions,
    }


def top_entities(db: Session, region: str | None = None, limit: int = 20) -> list[dict]:
    """Brightest nodes — drives the Knowledge Galaxy and graph highlights."""
    stmt = (
        select(Entity, func.count(MemoryEntity.memory_id).label("mentions"))
        .join(MemoryEntity, MemoryEntity.entity_id == Entity.id, isouter=True)
        .group_by(Entity.id)
        .order_by(func.coalesce(func.sum(Entity.weight), Entity.weight).desc(), Entity.weight.desc())
        .limit(limit)
    )
    if region:
        types = _TYPES_FOR_REGION.get(region, [])
        stmt = stmt.where(Entity.type.in_(types))

    out = []
    for ent, mentions in db.execute(stmt).all():
        out.append({
            "id": str(ent.id),
            "type": ent.type,
            "name": ent.name,
            "region": REGION_FOR_ENTITY.get(ent.type, "memory"),
            "weight": round(ent.weight, 3),
            "mentions": mentions,
        })
    return out
