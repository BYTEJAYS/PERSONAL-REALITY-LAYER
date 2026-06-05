"""Friend Feedback Loop (Reality OS).

Friends help the companion learn — but a friend's claim is hearsay, not truth, so
nothing they submit enters long-term memory until the owner confirms it. Submitted
facts land in QUARANTINE (stored inert: no embedding, no entity links, excluded
from the companion's answers). The owner reviews the queue; approving re-ingests
the claim as a real, attributed memory; rejecting discards it. Questions friends
ask are logged separately as signal for what to fill in.

This is the Confidence/Quarantine engine applied to crowd input. Pure
``classify_submission`` / ``assess_submission`` are unit-testable; the adapters
persist and promote.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from .confidence_engine import Evidence, score_confidence

QUARANTINE_SOURCE = "quarantine"     # inert holding pen — never read as truth
FRIEND_SOURCE = "friend-report"      # an approved, attributed friend contribution
QUESTION_SOURCE = "friend-question"  # logged questions (signal, not facts)

_CORRECTION = re.compile(
    r"\b(actually|not true|that's wrong|isn't|is not|correction|no he|no she|"
    r"incorrect|mistake)\b", re.I)
_QUESTION = re.compile(r"(\?\s*$)|^\s*(who|what|when|where|why|how|does|is|are|did|can)\b", re.I)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def classify_submission(text: str) -> str:
    """fact | correction | question — decides how it's handled."""
    t = (text or "").strip()
    if not t:
        return "empty"
    if _QUESTION.search(t):
        return "question"
    if _CORRECTION.search(t):
        return "correction"
    return "fact"


def assess_submission(text: str, submitter: str = "friend") -> dict:
    """Score how trustworthy a friend's claim is. Friend claims are single-source
    hearsay, so they quarantine by default — the score just helps the owner triage."""
    kind = classify_submission(text)
    conf = score_confidence(Evidence(sources=[FRIEND_SOURCE]))
    return {
        "kind": kind,
        "submitter": submitter,
        "confidence": conf["confidence"],
        "plausibility": conf["label"],
        # Facts/corrections are always held for review; questions are never facts.
        "status": "logged" if kind == "question" else "quarantined",
    }


# --- DB adapter -------------------------------------------------------------
def submit(db, text: str, submitter: str = "friend") -> dict:
    """Take a friend's contribution. Questions are logged; facts/corrections are
    stored INERT in quarantine (no embedding, no links) pending owner review."""
    from .models import Memory

    info = assess_submission(text, submitter)
    if info["kind"] == "empty":
        return {"ready": False, "error": "empty submission"}

    source = QUESTION_SOURCE if info["kind"] == "question" else QUARANTINE_SOURCE
    row = Memory(
        ts=_now(),
        source=source,
        title=(text.strip().split("\n", 1)[0])[:120],
        content=text.strip(),
        memory_type="episodic",
        importance=0.0,            # carries no weight while pending
        embedding=None,            # NOT embedded → invisible to semantic recall
        meta={"feedback": {**info, "reviewed": False}},
    )
    db.add(row)
    db.commit()

    if info["kind"] == "question":
        msg = "Thanks — noted. I'll let Jay know people are curious about that."
    else:
        msg = ("Thanks! I've passed that to Jay to confirm before I treat it as "
               "something I know about him.")
    return {
        "ready": True,
        "generated_at": _now().isoformat(),
        "id": str(row.id),
        "status": info["status"],
        "kind": info["kind"],
        "message": msg,
    }


def pending(db) -> dict:
    """Owner view: friend contributions awaiting review."""
    from sqlalchemy import select
    from .models import Memory

    rows = db.execute(
        select(Memory.id, Memory.ts, Memory.content, Memory.meta)
        .where(Memory.source == QUARANTINE_SOURCE).order_by(Memory.ts.desc())
    ).all()
    items = [{
        "id": str(mid),
        "submitted_at": ts.isoformat() if ts else None,
        "text": content,
        "submitter": (meta or {}).get("feedback", {}).get("submitter", "friend"),
        "kind": (meta or {}).get("feedback", {}).get("kind"),
        "plausibility": (meta or {}).get("feedback", {}).get("plausibility"),
    } for mid, ts, content, meta in rows]
    return {"ready": True, "generated_at": _now().isoformat(),
            "pending_count": len(items), "pending": items}


def questions(db, limit: int = 100) -> dict:
    """Owner view: what friends have been asking about you (curiosity signal)."""
    from sqlalchemy import select
    from .models import Memory

    rows = db.execute(
        select(Memory.ts, Memory.content, Memory.meta)
        .where(Memory.source == QUESTION_SOURCE).order_by(Memory.ts.desc()).limit(limit)
    ).all()
    items = [{"asked_at": ts.isoformat() if ts else None, "question": content,
              "submitter": (meta or {}).get("feedback", {}).get("submitter", "friend")}
             for ts, content, meta in rows]
    return {"ready": True, "generated_at": _now().isoformat(),
            "question_count": len(items), "questions": items}


def review(db, memory_id: str, approve: bool, importance: float = 0.5) -> dict:
    """Owner decision on a quarantined claim. Approve → re-ingest as a real,
    attributed, owner-verified memory (embedded + entity-linked). Reject → discard."""
    from .models import Memory

    row = db.get(Memory, memory_id)
    if row is None or row.source != QUARANTINE_SOURCE:
        return {"ready": False, "error": "no pending submission with that id"}

    fb = (row.meta or {}).get("feedback", {})
    text = row.content
    submitter = fb.get("submitter", "friend")
    db.delete(row)          # the inert quarantine row goes either way
    db.commit()

    if not approve:
        return {"ready": True, "id": str(memory_id), "decision": "rejected",
                "message": "Discarded — not added to memory."}

    # Promote into real memory through the single write path (gets embedding,
    # entity extraction, graph projection) with friend attribution + verification.
    from .memory_engine import MemoryInput, ingest
    mem = ingest(db, MemoryInput(
        ts=_now(),
        source=FRIEND_SOURCE,
        title=(text.split("\n", 1)[0])[:120],
        content=text,
        importance=importance,
        meta={"contributed_by": submitter, "verified": True},
    ))
    return {
        "ready": True,
        "decision": "approved",
        "new_memory_id": str(mem.id) if mem else None,
        "message": f"Added to memory, credited to {submitter} and marked verified.",
    }
