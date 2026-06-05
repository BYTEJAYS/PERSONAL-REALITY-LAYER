"""Companion endpoints — the friends-only 'best friend who knows Jay' voice.

Token-gated (owner or friend). Reasons from all of Jay's data but discloses with
a best-friend's discretion (no raw finances/medical/private reflections).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import companion
from ..auth import require_companion
from ..db import get_db

router = APIRouter(prefix="/companion", tags=["companion"])


class AskIn(BaseModel):
    question: str


@router.post("/ask")
def ask(body: AskIn, role: str = Depends(require_companion), db: Session = Depends(get_db)):
    """Ask Jay's companion about him — discreetly grounded in everything it knows."""
    return companion.ask(db, body.question)


@router.get("/about")
def about(role: str = Depends(require_companion)):
    """What this companion is, and what it will and won't share."""
    return {
        "name": "Jay's companion",
        "knows": "Jay's personality, emotions, values, story and how he tends to react.",
        "discretion": [
            "won't share exact finances or account balances",
            "won't share medical numbers",
            "won't quote his private reflections",
            "keeps family and friends' details vague",
        ],
        "your_role": role,
    }
