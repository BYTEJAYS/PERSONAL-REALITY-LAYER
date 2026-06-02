"""Bridge connectors → Memory Engine (the DB ingestion path)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from .connectors import registry
from .memory_engine import EntityRef, MemoryInput, ingest_many


def list_connectors() -> list[dict]:
    return [c.info() for c in registry.all_connectors()]


def run_connector(db: Session, name: str, **opts) -> dict:
    conn = registry.get(name)
    if conn is None:
        raise ValueError(f"unknown connector: {name}")
    if not conn.available():
        return {"connector": name, "error": "unavailable on this machine"}

    items = [
        MemoryInput(
            ts=rm.ts, source=rm.source, title=rm.title, content=rm.content,
            importance=rm.importance, memory_type=rm.memory_type,
            entities=[EntityRef(e.type, e.name, e.role) for e in rm.entities],
            location=rm.location, meta=rm.meta, dedupe_key=rm.dedupe_key,
        )
        for rm in conn.fetch(**opts)
    ]
    result = ingest_many(db, items)
    result["connector"] = name
    return result
