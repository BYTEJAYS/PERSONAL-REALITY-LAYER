from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import brain, graph
from ..db import get_db
from ..schemas import BrainState

router = APIRouter(prefix="/brain", tags=["brain"])


@router.get("/state", response_model=BrainState)
def get_brain_state(db: Session = Depends(get_db)):
    """Live cognitive state: region intensities driven by real memory counts."""
    state = brain.brain_state(db)
    state["neo4j"] = graph.ping()
    return state


@router.get("/entities")
def get_top_entities(
    db: Session = Depends(get_db),
    region: str | None = Query(None, pattern="^(memory|knowledge|project|goal|social)$"),
    limit: int = Query(20, le=100),
):
    """Brightest nodes (Knowledge Galaxy / Life Graph highlights)."""
    return brain.top_entities(db, region=region, limit=limit)


@router.get("/focus")
def focus(
    name: str,
    type: str = Query("project", pattern="^(person|project|goal|skill|place)$"),
    db: Session = Depends(get_db),
):
    """The 'Tell me about TGIE' fly-through: the entity's graph neighborhood."""
    return graph.neighborhood(type, name)
