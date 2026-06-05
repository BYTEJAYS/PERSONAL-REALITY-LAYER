"""Guided self-intake endpoints — owner-only. How Jay feeds his own data in.

Friends never touch these (the owner_guard middleware + require_owner keep them
owner-gated). Answers route into the engines that build the personal model.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import intake
from ..auth import require_owner
from ..db import get_db

router = APIRouter(prefix="/intake", tags=["intake"])


class AnswerIn(BaseModel):
    prompt_id: str
    text: str


class BioIn(BaseModel):
    text: str


@router.get("/prompts")
def prompts(role: str = Depends(require_owner)):
    """The guided intake questionnaire (high-signal prompts)."""
    return intake.prompt_set()


@router.post("/answer")
def answer(body: AnswerIn, role: str = Depends(require_owner), db: Session = Depends(get_db)):
    """Ingest one intake answer into the right engine (by the prompt's source)."""
    return intake.ingest_answer(db, body.prompt_id, body.text)


@router.post("/bio")
def bio(body: BioIn, role: str = Depends(require_owner), db: Session = Depends(get_db)):
    """Ingest your life story as a biography memory."""
    return intake.ingest_bio(db, body.text)
