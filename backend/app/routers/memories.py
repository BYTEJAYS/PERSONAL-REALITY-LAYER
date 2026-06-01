from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..embeddings import embed
from ..memory_engine import EntityRef, MemoryInput, ingest
from ..models import Memory
from ..schemas import MemoryIn, MemoryOut

router = APIRouter(prefix="/memories", tags=["memories"])


@router.post("", response_model=MemoryOut)
def create_memory(payload: MemoryIn, db: Session = Depends(get_db)):
    item = MemoryInput(
        ts=payload.ts, source=payload.source, title=payload.title, content=payload.content,
        location=payload.location, emotion=payload.emotion, importance=payload.importance,
        entities=[EntityRef(e.type, e.name, e.role) for e in payload.entities],
        meta=payload.meta, dedupe_key=payload.dedupe_key,
    )
    memory = ingest(db, item)
    if memory is None:  # duplicate — return the existing row
        memory = db.execute(
            select(Memory)
            .options(selectinload(Memory.links))
            .where(Memory.source == payload.source,
                   Memory.meta["dedupe_key"].astext == payload.dedupe_key)
        ).scalars().first()
    else:
        db.refresh(memory)
    return MemoryOut.from_model(memory)


@router.get("", response_model=list[MemoryOut])
def list_memories(
    db: Session = Depends(get_db),
    source: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
):
    stmt = select(Memory).options(selectinload(Memory.links)).order_by(Memory.ts.desc())
    if source:
        stmt = stmt.where(Memory.source == source)
    if since:
        stmt = stmt.where(Memory.ts >= since)
    if until:
        stmt = stmt.where(Memory.ts <= until)
    rows = db.execute(stmt.limit(limit).offset(offset)).scalars().all()
    return [MemoryOut.from_model(m) for m in rows]


@router.get("/search", response_model=list[MemoryOut])
def search_memories(
    q: str,
    db: Session = Depends(get_db),
    limit: int = Query(20, le=100),
):
    """Semantic search over memories using the pgvector cosine distance."""
    query_vec = embed(q)
    rows = db.execute(
        select(Memory)
        .options(selectinload(Memory.links))
        .order_by(Memory.embedding.cosine_distance(query_vec))
        .limit(limit)
    ).scalars().all()
    return [MemoryOut.from_model(m) for m in rows]
