"""Reflection Engine — the nightly look-back over a day's journal.

From a day's structured journal events it composes five honest sections:

    Wins         — what went well (achievements, positive moments)
    Challenges   — what was hard (struggles, negative emotions)
    Lessons      — gentle, evidence-tied takeaways
    Gratitude    — people who helped, good things to be thankful for
    Suggestions  — small, actionable nudges grounded in what happened

``reflect`` is pure and DB-free. If an LLM ``complete_fn`` is supplied it phrases
the reflection warmly from the *structured evidence* (never inventing facts);
otherwise a deterministic version is returned. ``reflect_day(db)`` pulls a day's
journal memories and calls it with the local model when available.

Conservative: a section with no evidence is simply empty — no fabrication.
"""

from __future__ import annotations

import re
from typing import Callable

from .emotional_cortex import valence
from .journal import JournalEvent

_ACHIEVE = re.compile(
    r"\b(finished|completed|won|achieved|built|shipped|launched|solved|cracked|"
    r"learned|started|aced|nailed|progress)\b", re.IGNORECASE)
_HELP = re.compile(
    r"\b(helped|supported|thanks|grateful|gave|taught|encouraged|listened)\b",
    re.IGNORECASE)
_LATE = re.compile(r"\b(late|2 ?am|3 ?am|midnight|couldn'?t sleep|insomnia)\b", re.IGNORECASE)


def reflect(events: list[JournalEvent], complete_fn: Callable[[str], str] | None = None) -> dict:
    """Compose a five-part reflection from a day's events."""
    if not events:
        return {"ready": False, "message": "No journal for this day to reflect on."}

    wins, challenges, gratitude = [], [], []
    lessons, suggestions = [], []
    seen_cat: set[str] = set()

    for e in events:
        v = valence(e.emotion or "")
        if _ACHIEVE.search(e.description) or v >= 0.5:
            wins.append(e.description)
        if _HELP.search(e.description):
            who = (" & ".join(e.people)) if e.people else None
            gratitude.append(e.description + (f" (thanks {who})" if who else ""))
        if v <= -0.4:
            challenges.append(e.description)

    # Lessons + suggestions: tied to the kind of challenge detected, not generic.
    cats = {e.category for e in events}
    stress = any(valence(e.emotion or "") <= -0.6 for e in events)
    fitness = "Fitness" in cats
    if stress:
        lessons.append("Deadlines and pressure hit hard today — pacing matters.")
        suggestions.append("Break tomorrow's big task into smaller, finishable pieces.")
    if any(e.category == "Relationships" and valence(e.emotion or "") < 0 for e in events):
        lessons.append("Friction with people lingers — worth circling back when calm.")
        suggestions.append("Reach out to smooth over the disagreement.")
    if any(_LATE.search(e.description) for e in events):
        suggestions.append("Try winding down earlier — sleep compounds.")
    if not fitness and stress:
        suggestions.append("A short workout tomorrow usually resets the mood.")
    if not lessons:
        lessons.append("A steady, ordinary day — those add up too.")

    structured = {
        "wins": wins[:6],
        "challenges": challenges[:6],
        "lessons": lessons[:4],
        "gratitude": gratitude[:4],
        "suggestions": suggestions[:4],
    }

    narrative = None
    if complete_fn is not None:
        try:
            narrative = _llm_narrative(structured, complete_fn)
        except Exception:
            narrative = None

    return {"ready": True, **structured, "narrative": narrative}


def _llm_narrative(structured: dict, complete_fn: Callable[[str], str]) -> str | None:
    bits = []
    for key in ("wins", "challenges", "lessons", "gratitude", "suggestions"):
        if structured[key]:
            bits.append(key.title() + ": " + "; ".join(structured[key]))
    if not bits:
        return None
    evidence = "\n".join(bits)
    prompt = (
        "You are the user's own reflective journal companion. Using ONLY the "
        "structured notes below, write a short (3-4 sentence), warm, honest "
        "end-of-day reflection in second person ('you'). Do not invent anything "
        "not present in the notes.\n\n" + evidence + "\n\nReflection:"
    )
    out = (complete_fn(prompt) or "").strip()
    return out or None


# --- DB adapter -------------------------------------------------------------
def reflect_day(db, day: str | None = None, use_llm: bool = True) -> dict:
    """Reflect on one day's journal (defaults to today, UTC)."""
    from datetime import datetime, timezone

    from .journal import JournalEvent, get_day

    day = day or datetime.now(timezone.utc).date().isoformat()
    bundle = get_day(db, day)
    if not bundle.get("ready"):
        return {"ready": False, "date": day, "message": "No journal entry for this day."}

    events: list[JournalEvent] = []
    for entry in bundle["entries"]:
        for e in entry.get("journal", {}).get("events", []):
            events.append(JournalEvent(
                category=e.get("category", "Life"),
                description=e.get("description", ""),
                emotion=e.get("emotion"),
                people=e.get("people", []),
                importance=e.get("importance", 0.5),
            ))

    complete_fn = None
    if use_llm:
        from . import llm
        if llm.available():
            complete_fn = lambda p: llm.complete(
                "You are the user's own honest, warm reflective journal companion.",
                p, max_tokens=220, temperature=0.6)

    result = reflect(events, complete_fn=complete_fn)
    result["date"] = day
    return result
