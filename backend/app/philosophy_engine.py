"""Philosophy Evolution & Contradiction Engine.

Wisdom must evolve. The Principle Engine already records *how* each principle
moved — formed, strengthened, weakened, revised, faded — with timestamps. This
engine reads that recorded history and turns it into two human views:

  Contradictions — where your beliefs collide or have flipped:
    • opposing   — two principles take opposite stances on the same thing
    • revision   — a principle was reworded into an updated belief
    • abandoned  — a principle you once held with conviction is fading out

  Evolution Timeline — a chronological account of how your thinking has changed,
    grouped by month, drawn from every principle's history.

Pure functions are DB-free and unit-tested; ``build(db)`` reads the stored
``source='principle'`` memories (read-only — it never mutates the principle set)
and assembles both views, with an optional LLM narrative when the model is up.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

_DECISION_KEY = re.compile(r"^decision:(.+):(pos|neg)$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def detect_contradictions(principles: list[dict]) -> list[dict]:
    """Surface opposing pairs, revised beliefs, and abandoned convictions."""
    out: list[dict] = []
    by_key = {p.get("key"): p for p in principles if p.get("key")}

    # 1) Opposing stances on the same decision axis (…:pos vs …:neg).
    seen_axes: set[str] = set()
    for p in principles:
        m = _DECISION_KEY.match(p.get("key", ""))
        if not m:
            continue
        axis, stance = m.group(1), m.group(2)
        if axis in seen_axes:
            continue
        opp_key = f"decision:{axis}:{'neg' if stance == 'pos' else 'pos'}"
        opp = by_key.get(opp_key)
        if opp:
            seen_axes.add(axis)
            winner = p if p.get("confidence", 0) >= opp.get("confidence", 0) else opp
            out.append({
                "type": "opposing",
                "axis": axis,
                "statements": [p.get("statement"), opp.get("statement")],
                "current_lean": winner.get("statement"),
                "detail": "Two opposite reads on the same thing — you currently lean toward "
                          f"“{winner.get('statement')}”.",
                "confidence": round(min(p.get("confidence", 0), opp.get("confidence", 0)), 3),
            })

    # 2) Per-principle: revisions and abandonment.
    for p in principles:
        hist = p.get("history", [])
        revisions = [h for h in hist if h.get("event") == "revised"]
        if revisions:
            last = revisions[-1]
            out.append({
                "type": "revision",
                "key": p.get("key"),
                "from": last.get("previous"),
                "to": last.get("statement"),
                "detail": f"You updated this belief: “{last.get('previous')}” "
                          f"→ “{last.get('statement')}”.",
            })
        if (p.get("status") in ("weakening", "dormant")
                and any(h.get("event") in ("strengthened", "formed") for h in hist)):
            out.append({
                "type": "abandoned",
                "key": p.get("key"),
                "statement": p.get("statement"),
                "detail": f"A principle you once held is fading: “{p.get('statement')}”.",
            })
    return out


def build_timeline(principles: list[dict]) -> tuple[list[dict], list[dict]]:
    """Flatten every principle's history into one chronological belief-event
    stream, plus a month-grouped view. Returns (events, periods)."""
    events: list[dict] = []
    for p in principles:
        for h in p.get("history", []):
            ts = h.get("ts") or ""
            events.append({
                "ts": ts,
                "period": ts[:7],  # YYYY-MM
                "key": p.get("key"),
                "category": p.get("category"),
                "event": h.get("event"),
                "confidence": h.get("confidence"),
                "statement": h.get("statement") or p.get("statement"),
            })
    events.sort(key=lambda e: e["ts"])

    periods: dict[str, list[dict]] = {}
    for e in events:
        periods.setdefault(e["period"], []).append(e)
    period_list = [{
        "period": k,
        "events": periods[k],
        "summary": _period_summary(periods[k]),
    } for k in sorted(periods)]
    return events, period_list


def _period_summary(events: list[dict]) -> str:
    counts: dict[str, int] = {}
    for e in events:
        counts[e["event"]] = counts.get(e["event"], 0) + 1
    parts = []
    label = {"formed": "formed", "strengthened": "strengthened",
             "weakened": "weakened", "revised": "revised", "faded": "faded"}
    for ev in ("formed", "strengthened", "revised", "weakened", "faded"):
        if counts.get(ev):
            n = counts[ev]
            parts.append(f"{n} {label[ev]}")
    return ", ".join(parts) or "no changes"


# --- DB adapter -------------------------------------------------------------
def _load_principles(db) -> list[dict]:
    from sqlalchemy import select

    from .models import Memory
    from .principle_engine import PRINCIPLE_SOURCE

    rows = db.execute(select(Memory).where(Memory.source == PRINCIPLE_SOURCE)).scalars().all()
    out = []
    for m in rows:
        p = (m.meta or {}).get("principle")
        if p and p.get("key"):
            out.append(p)
    return out


def build(db, use_llm: bool = True) -> dict:
    """Read the standing principles and assemble the contradiction + evolution views."""
    principles = _load_principles(db)
    contradictions = detect_contradictions(principles)
    events, periods = build_timeline(principles)

    narrative = None
    if use_llm and events:
        try:
            from . import llm
            if llm.available():
                lines = [f"{p['period']}: {p['summary']}" for p in periods]
                prompt = (
                    "These are month-by-month changes in a person's recorded life "
                    "principles. In 2-3 honest sentences, second person ('you'), "
                    "describe how their thinking has evolved. Use ONLY what's given; "
                    "don't invent.\n\n" + "\n".join(lines) + "\n\nReflection:"
                )
                out = llm.complete(
                    "You are the user's own reflective companion narrating how their "
                    "philosophy has evolved.", prompt, max_tokens=180, temperature=0.6)
                narrative = (out or "").strip() or None
        except Exception:
            narrative = None

    return {
        "generated_at": _now_iso(),
        "ready": bool(principles),
        "note": "How your principles have collided and evolved over time — read from "
                "the recorded history of each, never invented.",
        "contradiction_count": len(contradictions),
        "contradictions": contradictions,
        "timeline": periods,
        "narrative": narrative,
    }
