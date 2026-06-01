"""Memory Engine — the single write path for all reality.

ingest() takes a normalized signal from any source, embeds it, resolves its
entities, writes the canonical row + edges in Postgres, and projects the result
into the Neo4j Life Graph. Every connector funnels through here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import graph
from .embeddings import embed
from .models import Entity, Memory, MemoryEntity


@dataclass
class EntityRef:
    type: str  # person | project | goal | skill | place
    name: str
    role: str = "mentions"


@dataclass
class MemoryInput:
    ts: datetime
    source: str
    title: str
    content: str = ""
    location: dict | None = None
    emotion: str | None = None
    importance: float = 0.5
    entities: list[EntityRef] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    # Stable de-dup key (e.g. git commit sha) so re-ingesting is idempotent.
    dedupe_key: str | None = None
    # PCME memory type; classified from entities when left None.
    memory_type: str | None = None


def classify_memory_type(entities: list[EntityRef]) -> str:
    """Episodic | knowledge | social | goal, from the memory's entity mix."""
    persons = sum(1 for e in entities if e.type == "person")
    has_goal = any(e.type == "goal" for e in entities)
    has_project = any(e.type == "project" for e in entities)
    has_skill = any(e.type == "skill" for e in entities)
    if has_goal:
        return "goal"
    if persons >= 2:  # a real interaction, not just an author/owner
        return "social"
    if has_project:
        return "episodic"
    if has_skill:
        return "knowledge"
    return "episodic"


def _get_or_create_entity(db: Session, type_: str, name: str) -> Entity:
    name = name.strip()
    ent = db.execute(
        select(Entity).where(Entity.type == type_, Entity.name == name)
    ).scalar_one_or_none()
    if ent is None:
        ent = Entity(type=type_, name=name, weight=0.0)
        db.add(ent)
        db.flush()
    return ent


def _already_ingested(db: Session, source: str, dedupe_key: str) -> bool:
    return db.execute(
        select(Memory.id)
        .where(Memory.source == source, Memory.meta["dedupe_key"].astext == dedupe_key)
        .limit(1)
    ).first() is not None


def ingest(db: Session, item: MemoryInput) -> Memory | None:
    """Persist one memory. Returns None if it was a duplicate."""
    if item.dedupe_key and _already_ingested(db, item.source, item.dedupe_key):
        return None

    meta = dict(item.meta)
    if item.dedupe_key:
        meta["dedupe_key"] = item.dedupe_key

    text_for_embedding = f"{item.title}\n{item.content}".strip()
    memory = Memory(
        ts=item.ts,
        source=item.source,
        title=item.title[:512],
        content=item.content,
        memory_type=item.memory_type or classify_memory_type(item.entities),
        location=item.location,
        emotion=item.emotion,
        importance=item.importance,
        embedding=embed(text_for_embedding),
        meta=meta,
    )
    db.add(memory)
    db.flush()

    graph_entities: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for ref in item.entities:
        key = (ref.type, ref.name.strip().lower())
        if not ref.name.strip() or key in seen:
            continue
        seen.add(key)
        ent = _get_or_create_entity(db, ref.type, ref.name)
        ent.weight += item.importance
        db.add(MemoryEntity(memory_id=memory.id, entity_id=ent.id, role=ref.role))
        graph_entities.append({"type": ent.type, "name": ent.name, "role": ref.role})

    db.commit()

    graph.upsert_memory(
        memory_id=str(memory.id),
        title=memory.title,
        ts=memory.ts.isoformat(),
        entities=graph_entities,
    )
    return memory


def ingest_many(db: Session, items: list[MemoryInput]) -> dict:
    created, skipped = 0, 0
    for item in items:
        if ingest(db, item) is None:
            skipped += 1
        else:
            created += 1
    return {"created": created, "skipped": skipped}
