"""Journal Mode endpoints — daily reflection, timeline, and reviews.

All routes are owner-only (the global owner_guard middleware blocks friend
tokens from everything outside /companion). Journal content is stored under the
PRIVATE ``journal`` source, so even the owner's own companion never quotes it to
friends — it is the user's private record, surfaced only in their own chat.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import journal, reflection_engine, reviews
from ..db import get_db
from ..schemas import JournalIn

router = APIRouter(prefix="/journal", tags=["journal"])


@router.post("")
def add_journal(payload: JournalIn, db: Session = Depends(get_db)):
    """Record a journal entry. It's stored raw and mined into structured events
    that feed the emotion, social, habit, goal, and timeline engines."""
    return journal.add_entry(
        db, payload.text, ts=payload.ts, importance=payload.importance,
        emotion=payload.emotion, location=payload.location, title=payload.title,
    )


@router.get("")
def get_timeline(days: int = Query(30, ge=1, le=3650), db: Session = Depends(get_db)):
    """Recent journal entries grouped by day (newest first)."""
    return journal.timeline(db, days=days)


@router.get("/day/{day}")
def get_day(day: str, db: Session = Depends(get_db)):
    """All entries (with extracted events) for one YYYY-MM-DD."""
    return journal.get_day(db, day)


@router.get("/reflection")
def get_reflection(
    date: str | None = Query(None, description="YYYY-MM-DD; defaults to today"),
    db: Session = Depends(get_db),
):
    """Nightly reflection: wins, challenges, lessons, gratitude, suggestions."""
    return reflection_engine.reflect_day(db, day=date)


@router.get("/review/month")
def get_month_review(
    month: str | None = Query(None, description="YYYY-MM; defaults to this month"),
    db: Session = Depends(get_db),
):
    """Monthly review: mood, where life went, people, skills, growth score."""
    return reviews.month(db, ym=month)


@router.get("/review/year")
def get_year_review(
    year: int | None = Query(None, description="YYYY; defaults to this year"),
    db: Session = Depends(get_db),
):
    """Yearly review: the above plus life chapters rolled from the months."""
    return reviews.year(db, y=year)
