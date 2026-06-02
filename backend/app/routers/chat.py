from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import query_engine
from ..db import get_db
from ..schemas import ChatIn, ChatOut

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatOut)
def chat(payload: ChatIn, db: Session = Depends(get_db)):
    """Ask the second brain. Answers are grounded in real memories with citations.

    Examples: "Where was I yesterday?", "What project consumed most of my time
    last month?", "When did I first get interested in machine learning?",
    "What projects am I neglecting?"
    """
    history = [{"role": t.role, "content": t.content} for t in payload.history]
    ans = query_engine.ask(db, payload.message, history=history)
    return ChatOut(
        answer=ans.answer,
        intent=ans.intent,
        llm_used=ans.llm_used,
        citations=[asdict(c) for c in ans.citations],
        data=ans.data,
    )
