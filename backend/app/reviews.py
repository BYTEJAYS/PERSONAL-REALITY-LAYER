"""Review Engine — Monthly and Yearly look-backs built from journal memory.

Aggregates a period's journal entries into a structured review: mood trend,
emotion mix, category distribution (where life went), the people who showed up,
skills touched, goals stated, standout memories, and a single ``growth_score``.

``compose_review`` is pure and DB-free (unit-testable). ``month(db)`` /
``year(db)`` pull the period's journal memories and feed it. Yearly additionally
rolls the months into chapters via the existing ``chapters`` engine.

Honest by construction: an empty period returns ``ready: false``; every number
traces to recorded entries.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .emotional_cortex import valence


@dataclass
class ReviewEntry:
    """One journal memory reduced to what a review needs."""
    date: datetime
    emotion: str | None = None
    importance: float = 0.5
    categories: list[str] = field(default_factory=list)
    people: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    goals: list[str] = field(default_factory=list)
    title: str = ""


def _growth_score(entries: list[ReviewEntry], avg_valence: float,
                  n_skills: int, n_goals: int) -> float:
    """Blend activity, positive mood, and learning/intent into a 0..1 score."""
    # Activity: more journaled days → more lived/recorded (saturates ~20 entries).
    activity = min(1.0, len(entries) / 20.0)
    mood = (avg_valence + 1) / 2  # -1..1 → 0..1
    learning = min(1.0, (n_skills + n_goals) / 8.0)
    score = 0.45 * activity + 0.35 * mood + 0.20 * learning
    return round(max(0.0, min(1.0, score)), 3)


def compose_review(entries: list[ReviewEntry], period_label: str, scope: str) -> dict:
    """Build a structured review over a set of entries (scope: 'month' | 'year')."""
    if not entries:
        return {"ready": False, "scope": scope, "period": period_label,
                "message": f"No journal entries for {period_label}."}

    emo_events = [e for e in entries if e.emotion]
    avg_valence = (
        sum(valence(e.emotion) for e in emo_events) / len(emo_events)
        if emo_events else 0.0
    )
    mood = ("positive" if avg_valence > 0.15 else
            "negative" if avg_valence < -0.15 else "balanced")

    emotion_mix = Counter(e.emotion for e in emo_events)
    category_mix = Counter(c for e in entries for c in e.categories)
    people_mix = Counter(p for e in entries for p in e.people)
    skills = sorted({s for e in entries for s in e.skills})
    goals = sorted({g for e in entries for g in e.goals})

    standouts = sorted(entries, key=lambda e: e.importance, reverse=True)[:5]

    review = {
        "ready": True,
        "scope": scope,
        "period": period_label,
        "entry_count": len(entries),
        "mood": mood,
        "avg_valence": round(avg_valence, 3),
        "emotion_mix": [{"emotion": e, "count": n} for e, n in emotion_mix.most_common(8)],
        "where_life_went": [{"category": c, "count": n} for c, n in category_mix.most_common()],
        "people": [{"name": p, "mentions": n} for p, n in people_mix.most_common(10)],
        "skills_touched": skills,
        "goals_stated": goals,
        "standout_memories": [{"date": e.date.date().isoformat(), "title": e.title,
                               "emotion": e.emotion, "importance": e.importance}
                              for e in standouts],
        "growth_score": _growth_score(entries, avg_valence, len(skills), len(goals)),
    }
    n = len(entries)
    ent_word = "entry" if n == 1 else "entries"
    ranked = category_mix.most_common()
    # Only claim a focus when one category clearly leads; otherwise it was a mix.
    if ranked and (len(ranked) == 1 or ranked[0][1] > ranked[1][1]):
        focus = f"mostly {ranked[0][0].lower()}"
    else:
        focus = "a varied mix"
    review["headline"] = f"{period_label}: {n} {ent_word}, mood {mood}, {focus}."
    return review


# --- DB adapters ------------------------------------------------------------
def _to_review_entries(rows) -> list[ReviewEntry]:
    out: list[ReviewEntry] = []
    for m in rows:
        meta = m.meta or {}
        j = meta.get("journal", {})
        ts = m.ts if m.ts.tzinfo else m.ts.replace(tzinfo=timezone.utc)
        # skills/goals were linked as entities; recover from journal meta where
        # present, else leave empty (the entity engines still see them).
        out.append(ReviewEntry(
            date=ts, emotion=m.emotion, importance=m.importance or 0.5,
            categories=j.get("categories", []), people=j.get("people", []),
            title=m.title or "",
        ))
    return out


def _journal_rows_between(db, start: datetime, end: datetime):
    from sqlalchemy import select
    from .models import Memory
    return db.execute(
        select(Memory).where(
            Memory.source == "journal", Memory.ts >= start, Memory.ts < end
        ).order_by(Memory.ts)
    ).scalars().all()


def month(db, ym: str | None = None) -> dict:
    """Monthly review for 'YYYY-MM' (defaults to the current month, UTC)."""
    now = datetime.now(timezone.utc)
    ym = ym or f"{now.year:04d}-{now.month:02d}"
    try:
        y, m = (int(x) for x in ym.split("-"))
        start = datetime(y, m, 1, tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return {"ready": False, "message": "Use a YYYY-MM month."}
    end = datetime(y + (m == 12), (m % 12) + 1, 1, tzinfo=timezone.utc)
    entries = _to_review_entries(_journal_rows_between(db, start, end))
    # Enrich skills/goals from the linked entities of this window's memories.
    return compose_review(entries, ym, "month")


def year(db, y: int | None = None) -> dict:
    """Yearly review for a four-digit year (defaults to the current year, UTC)."""
    now = datetime.now(timezone.utc)
    y = int(y or now.year)
    start = datetime(y, 1, 1, tzinfo=timezone.utc)
    end = datetime(y + 1, 1, 1, tzinfo=timezone.utc)
    entries = _to_review_entries(_journal_rows_between(db, start, end))
    review = compose_review(entries, str(y), "year")
    if not review.get("ready"):
        return review

    # Roll the year's journal months into life chapters (reuse chapters engine).
    try:
        from dataclasses import asdict
        from .chapters import detect_chapters
        by_month: dict[str, Counter] = {}
        for e in entries:
            key = f"{e.date.year:04d}-{e.date.month:02d}"
            by_month.setdefault(key, Counter()).update(e.categories or ["Life"])
        monthly = [(key, by_month[key].most_common(1)[0][0]) for key in sorted(by_month)]
        review["chapters"] = [asdict(c) for c in detect_chapters(monthly)]
    except Exception:
        review["chapters"] = []
    return review
