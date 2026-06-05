"""Reality OS endpoints — the active, self-organising cognitive layer.

Importance/Confidence/Economy score and value memories; Versioning preserves
temporal truth; Curiosity turns gaps into questions; the Reality Compiler lowers
raw life through to wisdom. Empty stores return ``ready: false``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import (
    agents, confidence_engine, curiosity_engine, event_simulator, importance_engine,
    memory_economy, provenance, reality_compiler, self_evolution, thought_capture,
    versioning, world_model,
)
from ..db import get_db

router = APIRouter(prefix="/reality", tags=["reality"])


class CaptureIn(BaseModel):
    text: str


class AskIn(BaseModel):
    query: str


@router.get("/importance")
def get_importance(apply: bool = False, db: Session = Depends(get_db)):
    """Importance Engine: multi-factor importance score per memory."""
    return importance_engine.build(db, apply=apply)


@router.get("/confidence")
def get_confidence(db: Session = Depends(get_db)):
    """Confidence Engine: trust score + provenance; quarantines low-confidence claims."""
    return confidence_engine.build(db)


@router.get("/economy")
def get_economy(db: Session = Depends(get_db)):
    """Memory Economy: value = importance × confidence × relationship ÷ storage cost."""
    return memory_economy.build(db)


@router.get("/versioning")
def get_versioning(attribute: str | None = None, db: Session = Depends(get_db)):
    """Memory Versioning: temporal truth chains (Git for reality)."""
    return versioning.build(db, attribute=attribute)


@router.get("/curiosity")
def get_curiosity(db: Session = Depends(get_db)):
    """Curiosity Engine: questions from unknown people, repeated topics, timeline gaps."""
    return curiosity_engine.build(db)


@router.get("/compile")
def get_compile(db: Session = Depends(get_db)):
    """Reality Compiler: lower raw life → features → … → wisdom, with reductions."""
    return reality_compiler.compile(db)


@router.get("/world")
def get_world(domain: str | None = None, db: Session = Depends(get_db)):
    """Personal World Model: unified life-state across all domains (or one domain)."""
    return world_model.query(db, domain) if domain else world_model.build(db)


@router.get("/agents")
def get_agents():
    """Multi-Agent Society: the standing roster of specialist agents."""
    return {"agents": agents.roster()}


@router.post("/ask")
def post_ask(body: AskIn, db: Session = Depends(get_db)):
    """Convene the council of specialists relevant to a question."""
    return agents.dispatch(db, body.query)


@router.get("/evolution")
def get_evolution(db: Session = Depends(get_db)):
    """Self-Evolution: how PRL has personalised its importance weights to you."""
    return self_evolution.build(db)


@router.get("/provenance/{memory_id}")
def get_provenance(memory_id: str, db: Session = Depends(get_db)):
    """Source Attribution: where one memory came from + its audit trail."""
    return provenance.build(db, memory_id)


@router.get("/provenance")
def get_coverage(db: Session = Depends(get_db)):
    """Source Attribution coverage: how auditable the whole store is."""
    return provenance.coverage(db)


@router.get("/simulate")
def get_simulate(scenario: str | None = None, db: Session = Depends(get_db)):
    """Event Simulator: project a what-if scenario over your current life-state."""
    return event_simulator.build(db, scenario=scenario)


@router.post("/capture")
def post_capture(body: CaptureIn, db: Session = Depends(get_db)):
    """Dream/Thought Capture: preserve a fleeting idea as a classified memory."""
    return thought_capture.capture(db, body.text)
