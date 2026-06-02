"""The "you-model" voice: condition the language layer on who the user is.

A second brain shouldn't sound like a generic assistant — it should reason and
speak the way *you* would. The reasoning brain (preference/decision models) is
built separately and from scratch; this module is the lighter half: it pulls
the cognitive twin (traits + knowledge) and renders it into a system prompt so
the language layer frames every answer through your patterns.

DB-derived but cheap; cached briefly so chat turns don't each rebuild the twin.
Degrades to a neutral-but-grounded prompt if the twin can't be built.
"""

from __future__ import annotations

import time

from sqlalchemy.orm import Session

from . import cognitive_model, self_model

# (prompt, built_at) — short TTL so it tracks new memories without rebuilding
# the twin on every single chat turn.
_cache: tuple[str, float] | None = None
_TTL_SECONDS = 300


_BASE = (
    "You are PRL — this person's second brain. You are not a generic assistant; "
    "you are an extension of their own mind, built from their real history.\n\n"
    "Hard rules:\n"
    "- Ground EVERY claim in the evidence provided. Never invent a memory, date, "
    "project, or person. If the evidence is thin, say so plainly.\n"
    "- Cite the concrete memories you used (by title/date) when you make a factual claim.\n"
    "- Be concise and direct. Speak to them as 'you'. No corporate filler, no hedging "
    "for its own sake, no moralising.\n"
    "- When they ask for a decision or a judgement, don't just summarise — reason it "
    "through the lens of who they actually are (below) and commit to a view, while "
    "showing the tradeoff."
)


def _render(twin: dict) -> str:
    traits = twin.get("traits") or []
    summary = (twin.get("summary") or "").strip()
    knowledge = twin.get("knowledge_distribution") or []

    lines = [_BASE]
    if summary and "not enough data" not in summary.lower():
        lines.append("\nWho they are (learned from their own history):\n" + summary)

    if traits:
        trait_bits = []
        for t in traits:
            label = t.get("label")
            name = (t.get("name") or "").replace("_", " ")
            if label:
                trait_bits.append(f"- {name}: {label}")
        if trait_bits:
            lines.append("\nTheir patterns:\n" + "\n".join(trait_bits))

    if knowledge:
        top = ", ".join(k["skill"] for k in knowledge[:8] if k.get("skill"))
        if top:
            lines.append(f"\nWhat they work in: {top}.")

    lines.append(
        "\nReason and phrase your answer the way this person would think about it — "
        "match their priorities and patterns — but stay strictly grounded in the evidence."
    )
    return "\n".join(lines)


def system_prompt(db: Session) -> str:
    """Build (and briefly cache) the persona-conditioned system prompt."""
    global _cache
    now = time.monotonic()
    if _cache and (now - _cache[1]) < _TTL_SECONDS:
        return _cache[0]
    try:
        twin = cognitive_model.build(db)
        prompt = _render(twin)
    except Exception:
        prompt = _BASE  # never let twin-building break chat
    # Fold in the self-model: their own words + where those clash with behaviour.
    try:
        section = self_model.persona_section(db)
        if section:
            prompt += "\n\n" + section
    except Exception:
        pass
    _cache = (prompt, now)
    return prompt


def invalidate() -> None:
    """Drop the cache (call after a big ingest so the voice refreshes)."""
    global _cache
    _cache = None
