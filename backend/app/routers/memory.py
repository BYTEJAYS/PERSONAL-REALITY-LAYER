"""Memory-Architecture endpoints — the "store meaning, not bytes" subsystem.

These expose PRL's cognitive-compression layer: collapsing isolated memories into
events, aging detail down over time (intelligent forgetting), and eliminating
near-duplicate copies. Empty stores return ``ready: false`` rather than inventing
anything.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import (
    compressor, dedup, events, fractal, memory_aging, patterns, reconstructor,
    time_machine,
)
from ..db import get_db

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/events")
def get_events(db: Session = Depends(get_db)):
    """Event-Centric Memory: collapse isolated memories into meaningful events."""
    return events.build(db)


@router.get("/aging")
def get_aging(db: Session = Depends(get_db)):
    """Memory Aging: tier distribution, meaning-compression ratio, raw expiry."""
    return memory_aging.build(db)


@router.get("/duplicates")
def get_duplicates(db: Session = Depends(get_db)):
    """Duplicate Elimination: near-duplicate groups + master/diff storage savings."""
    return dedup.build(db)


@router.get("/patterns")
def get_patterns(db: Session = Depends(get_db)):
    """Pattern-Based Memory: the typical day + only the exceptions worth storing."""
    return patterns.build(db)


@router.get("/fractal")
def get_fractal(db: Session = Depends(get_db)):
    """Fractal Memory: Life → Era → Year → Event hierarchy for zooming in/out."""
    return fractal.build(db)


@router.get("/compress")
def preview_compress(use_llm: bool = True, db: Session = Depends(get_db)):
    """Preview the compaction plan (dry run) — no writes."""
    return compressor.run(db, dry_run=True, use_llm=use_llm)


@router.post("/compress")
def apply_compress(use_llm: bool = True, db: Session = Depends(get_db)):
    """Execute compaction: write event summaries + Memory DNA into meta (non-destructive)."""
    return compressor.run(db, dry_run=False, use_llm=use_llm)


@router.get("/reconstruct")
def list_reconstructable(db: Session = Depends(get_db)):
    """List memories that carry compressed Memory DNA and can be reconstructed."""
    return reconstructor.list_reconstructable(db)


@router.get("/reconstruct/{memory_id}")
def reconstruct_one(memory_id: str, use_llm: bool = True, db: Session = Depends(get_db)):
    """Generatively recreate a rich recollection from a memory's compressed DNA."""
    return reconstructor.reconstruct(db, memory_id, use_llm=use_llm)


@router.get("/timemachine")
def time_machine_views(db: Session = Depends(get_db)):
    """Time Machine: navigable day / month / year / decade views of the whole life."""
    return time_machine.build(db)


@router.get("/timemachine/{scale}/{key}")
def time_machine_zoom(scale: str, key: str, db: Session = Depends(get_db)):
    """Zoom into one period (e.g. scale=year key=2025) and list its memories."""
    return time_machine.navigate(db, scale, key)
