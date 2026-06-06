"""Companion endpoints — the friends-only 'best friend who knows Jay' voice.

Token-gated (owner or friend). Reasons from all of Jay's data but discloses with
a best-friend's discretion (no raw finances/medical/private reflections).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import companion, feedback
from ..auth import require_companion, require_owner
from ..db import get_db

router = APIRouter(prefix="/companion", tags=["companion"])


class ChatTurn(BaseModel):
    role: str   # "user" | "assistant"
    content: str


class AskIn(BaseModel):
    question: str
    history: list[ChatTurn] = []   # prior turns, oldest→newest, for continuity


class ContributeIn(BaseModel):
    text: str
    submitter: str = "friend"


class ReviewIn(BaseModel):
    memory_id: str
    approve: bool
    importance: float = 0.5


@router.post("/ask")
def ask(body: AskIn, role: str = Depends(require_companion), db: Session = Depends(get_db)):
    """Ask Jay's companion about him — discreetly grounded in everything it knows."""
    # Keep only the most recent turns so the prompt stays small.
    history = [{"role": t.role, "content": t.content} for t in body.history][-6:]
    return companion.ask(db, body.question, history=history)


@router.post("/contribute")
def contribute(body: ContributeIn, role: str = Depends(require_companion),
               db: Session = Depends(get_db)):
    """A friend shares something about Jay. Held in quarantine until Jay confirms."""
    return feedback.submit(db, body.text, body.submitter)


@router.get("/pending")
def pending(role: str = Depends(require_owner), db: Session = Depends(get_db)):
    """Owner: friend contributions awaiting your review."""
    return feedback.pending(db)


@router.get("/questions")
def friend_questions(role: str = Depends(require_owner), db: Session = Depends(get_db)):
    """Owner: what friends have been asking about you."""
    return feedback.questions(db)


@router.post("/review")
def review(body: ReviewIn, role: str = Depends(require_owner), db: Session = Depends(get_db)):
    """Owner: approve (→ real, attributed memory) or reject a quarantined claim."""
    return feedback.review(db, body.memory_id, body.approve, body.importance)


@router.get("/about")
def about(role: str = Depends(require_companion)):
    """What this companion is, and what it will and won't share."""
    return {
        "name": companion.COMPANION_NAME,
        "is": f"{companion.OWNER_NAME}'s companion",
        "knows": f"{companion.OWNER_NAME}'s personality, emotions, values, story and "
                 "how he tends to react.",
        "discretion": [
            "won't share exact finances or account balances",
            "won't share medical numbers",
            "won't quote his private reflections",
            "keeps family and friends' details vague",
        ],
        "your_role": role,
    }
