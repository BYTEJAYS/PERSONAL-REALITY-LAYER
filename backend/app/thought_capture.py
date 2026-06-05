"""Dream & Thought Capture Engine (Reality OS) — #16, PARTIAL → BUILT.

Most fleeting ideas — shower thoughts, dreams, ambitions, questions — vanish
forever. This is a fast capture path that classifies a raw jotting into its kind,
gauges urgency, and pulls out any goal, so the spark is preserved as a first-class
memory instead of lost.

Pure ``classify_capture`` is DB-free and unit-testable; ``capture(db, text)``
persists it through the Memory Engine.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

# Ordered: first matching kind wins.
_KIND_PATTERNS = [
    ("dream", re.compile(r"\b(i dreamt|i dreamed|in my dream|last night i dreamt|nightmare)\b", re.I)),
    ("question", re.compile(r"(\?$)|\b(what if|why do|how might|i wonder|could i|should i)\b", re.I)),
    ("ambition", re.compile(r"\b(someday|one day|i want to become|my dream is|bucket list|i aspire)\b", re.I)),
    ("idea", re.compile(r"\b(idea|what if we|we could|app that|build a|concept|prototype)\b", re.I)),
    ("todo", re.compile(r"\b(need to|have to|must|remember to|todo|to-do|don't forget)\b", re.I)),
]
_URGENT = re.compile(r"\b(urgent|asap|today|now|immediately|tonight|deadline)\b", re.I)
_GOAL_OPENER = re.compile(
    r"\b(i want to|my goal is to|i plan to|i'm going to|i aim to|i aspire to)\s+(.+)", re.I)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def classify_capture(text: str) -> dict:
    """Classify a raw capture into kind / urgency / goal."""
    t = (text or "").strip()
    if not t:
        return {"kind": "empty", "urgency": "none", "goal": None}

    kind = "spark"  # default: an undirected creative spark
    for name, pat in _KIND_PATTERNS:
        if pat.search(t):
            kind = name
            break

    urgency = "high" if _URGENT.search(t) else "normal"

    goal = None
    m = _GOAL_OPENER.search(t)
    if m:
        goal = re.sub(r"\s+", " ", m.group(2)).strip().rstrip(".!").strip()
        # An explicit "I want to…" is an ambition unless it's clearly a
        # dream / question / urgent todo.
        if kind in ("spark", "idea"):
            kind = "ambition"

    return {"kind": kind, "urgency": urgency, "goal": goal}


# --- DB adapter -------------------------------------------------------------
# Capture kind → PCME memory type.
_TYPE_FOR = {"dream": "episodic", "question": "knowledge", "ambition": "goal",
             "idea": "knowledge", "todo": "goal", "spark": "episodic"}


def capture(db, text: str, importance: float = 0.4) -> dict:
    from .memory_engine import EntityRef, MemoryInput, ingest

    info = classify_capture(text)
    if info["kind"] == "empty":
        return {"ready": False, "error": "empty capture"}

    entities = []
    if info["goal"]:
        entities.append(EntityRef(type="goal", name=info["goal"][:256]))

    title = (text.strip().split("\n", 1)[0])[:120]
    mem = ingest(db, MemoryInput(
        ts=_now(),
        source="capture",
        title=title,
        content=text.strip(),
        importance=0.6 if info["urgency"] == "high" else importance,
        memory_type=_TYPE_FOR.get(info["kind"], "episodic"),
        entities=entities,
        meta={"capture_kind": info["kind"], "urgency": info["urgency"]},
    ))
    return {
        "ready": True,
        "generated_at": _now().isoformat(),
        "captured": mem is not None,
        "memory_id": str(mem.id) if mem else None,
        **info,
    }
