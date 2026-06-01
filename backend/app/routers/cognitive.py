from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import cognitive_model, pattern_engine, prediction_engine, trend_engine
from ..db import get_db

router = APIRouter(prefix="/cognitive", tags=["cognitive"])


@router.get("/patterns")
def get_patterns(db: Session = Depends(get_db)):
    """Discovered behavioural correlations (contemporaneous + time-lagged)."""
    return pattern_engine.discover(db)


@router.get("/model")
def get_model(db: Session = Depends(get_db)):
    """The digital twin: evidence-backed traits + knowledge distribution."""
    return cognitive_model.build(db)


@router.get("/predictions")
def get_predictions(db: Session = Depends(get_db)):
    """Probabilistic forecasts (burnout, completion, decay, habit stability)."""
    return prediction_engine.forecast(db)


@router.get("/trends")
def get_trends(window_days: int = 30, db: Session = Depends(get_db)):
    """How the person is changing: rising / fading / emerging / dormant interests."""
    return trend_engine.build(db, window_days=window_days)
