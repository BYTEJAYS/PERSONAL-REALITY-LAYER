"""Reality OS endpoints — the active, self-organising cognitive layer.

Importance/Confidence/Economy score and value memories; Versioning preserves
temporal truth; Curiosity turns gaps into questions; the Reality Compiler lowers
raw life through to wisdom. Empty stores return ``ready: false``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import (
    confidence_engine, curiosity_engine, importance_engine, memory_economy,
    reality_compiler, versioning,
)
from ..db import get_db

router = APIRouter(prefix="/reality", tags=["reality"])


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
