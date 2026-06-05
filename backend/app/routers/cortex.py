"""Life-domain cortex endpoints — the Ledger's Finance / Health / Family views.

Each reads structured records mined into memory metadata (via text ingestion)
and returns an organised, evidence-backed summary. Empty domains return
``ready: false`` rather than fabricating anything.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import (
    behaviour_cortex, emotional_cortex, family_cortex, finance_cortex,
    health_cortex, social_cortex,
)
from ..db import get_db

router = APIRouter(prefix="/cortex", tags=["cortex"])


@router.get("/finance")
def get_finance(db: Session = Depends(get_db)):
    """Finance Cortex: spend trend, top categories, recurring bills + next due, anomalies."""
    return finance_cortex.build(db)


@router.get("/health")
def get_health(db: Session = Depends(get_db)):
    """Health Cortex: active medications, visits, test trends, refill/check-up reminders."""
    return health_cortex.build(db)


@router.get("/family")
def get_family(db: Session = Depends(get_db)):
    """Family Cortex: relationships, preserved stories/recipes, important dates + reminders."""
    return family_cortex.build(db)


@router.get("/emotional")
def get_emotional(db: Session = Depends(get_db)):
    """Emotional Cortex: overall mood, emotion mix, mood timeline, stress trend."""
    return emotional_cortex.build(db)


@router.get("/social")
def get_social(db: Session = Depends(get_db)):
    """Social Cortex: interaction frequency, inner circle, drifting contacts."""
    return social_cortex.build(db)


@router.get("/behaviour")
def get_behaviour(db: Session = Depends(get_db)):
    """Behaviour Cortex: focus window, weekday profile, routine consistency."""
    return behaviour_cortex.build(db)
