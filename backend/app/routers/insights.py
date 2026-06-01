from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import insight_engine
from ..db import get_db

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("")
def get_insights(db: Session = Depends(get_db)):
    """Generated observations about the user's life, each with its evidence.

    Examples it can surface: peak productivity time, primary focus project,
    neglected projects, whether learning happens inside project work,
    collaboration payoff, and activity momentum.
    """
    insights = insight_engine.generate(db)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(insights),
        "insights": [asdict(i) for i in insights],
    }
