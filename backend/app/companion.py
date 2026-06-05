"""Companion mode — the discreet 'best friend who knows you' (Reality OS).

This is the friend-facing voice of PRL. It is informed by 100% of the owner's
data (it genuinely knows them), but it has a real friend's discretion: it never
recites exact finances, medical readings, or quotes the owner's private
self-analysis, and it softens details about third parties (family, friends) who
never consented to being queried. It reasons from everything; it discloses
carefully.

Redaction happens BEFORE the model sees the evidence, so even a careless model
cannot leak raw records. The LLM narrates when available; a deterministic, warm
fallback answers otherwise. Pure helpers are DB-free and unit-testable.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

# PRL's companion identity. JERRY is derived from the owner's name, JAY.
COMPANION_NAME = "Jerry"
OWNER_NAME = "Jay"

# Sources whose RAW text must never be shown to friends (the owner's private inner life).
PRIVATE_SOURCES = {"self-analysis", "journal", "diary", "reflection"}
# Metadata domains carrying sensitive records — stripped from friend-facing evidence.
SENSITIVE_META = ("finance", "health")

_MONEY = re.compile(r"(₹|rs\.?|inr|\$)\s?[\d,]+(\.\d+)?", re.I)
_MEDICAL = re.compile(r"\b\d+(\.\d+)?\s?(mg/dl|mg|bpm|kg|mmhg|%)\b", re.I)
_BIGNUM = re.compile(r"\b\d{4,}\b")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def mask_numbers(text: str) -> str:
    """Replace exact money / medical / large figures with qualitative placeholders."""
    if not text:
        return text
    t = _MONEY.sub("[an amount]", text)
    t = _MEDICAL.sub("[a reading]", t)
    t = _BIGNUM.sub("[a number]", t)
    return t


def qualitative_money(savings_rate: float | None, trend: str | None) -> str:
    """How a discreet friend describes someone's money situation — no figures."""
    if savings_rate is None:
        return "he doesn't really talk numbers, but he gets by"
    if savings_rate >= 0.2:
        return "he's been pretty comfortable lately"
    if savings_rate >= 0.05:
        return "he's managing — a bit careful with money but fine"
    if trend == "rising":
        return "money's a little tight right now, spending's crept up"
    return "he's been a bit stretched lately, honestly"


def redact_evidence(rows: list[dict]) -> list[dict]:
    """Make retrieved memories safe to put in front of a friend-facing model."""
    safe = []
    for r in rows:
        source = (r.get("source") or "").strip().lower()
        if source in PRIVATE_SOURCES:
            # Acknowledge it exists, never expose the words.
            safe.append({"title": "(a private reflection)",
                         "content": "Jay has worked through some personal feelings here.",
                         "source": source})
            continue
        meta = {k: v for k, v in (r.get("meta") or {}).items() if k not in SENSITIVE_META}
        safe.append({
            "title": mask_numbers(r.get("title", "")),
            "content": mask_numbers(r.get("content", "")),
            "source": source,
            "meta": meta,
        })
    return safe


def disclosure_policy() -> str:
    """System-prompt addendum that enforces a best-friend's discretion."""
    return (
        f"You are speaking to {OWNER_NAME}'s FRIENDS as the one who knows him best. "
        "You know everything about him, but you are discreet, the way a real best "
        "friend is:\n"
        f"- Your name is {COMPANION_NAME}; if asked who you are, say you're "
        f"{OWNER_NAME}'s companion.\n"
        "- Never state exact money amounts, account balances, or medical numbers.\n"
        "- Never quote or paraphrase his private journal / self-analysis.\n"
        "- Speak about his feelings, values and how he'd react warmly and honestly.\n"
        "- Protect his family and friends — keep their details vague.\n"
        "- If asked for something private and specific, gently deflect: that's his "
        f"to share. Be warm, real, refer to him as '{OWNER_NAME}', never clinical."
    )


def friend_system_prompt(persona_summary: str = "") -> str:
    base = (f"You are {COMPANION_NAME} — {OWNER_NAME}'s companion, an AI who deeply "
            f"understands {OWNER_NAME}: his personality, emotions, values, and how he "
            f"tends to react. You always identify yourself as {COMPANION_NAME}.")
    if persona_summary:
        base += f"\n\nWhat you know about {OWNER_NAME}:\n{persona_summary}"
    return base + "\n\n" + disclosure_policy()


# Only volunteer his current mood when the question is actually about how he's
# doing/feeling — otherwise it reads as a bolted-on, repetitive opener.
_FEELING_RX = re.compile(
    r"\b(feel|feeling|feels|doing|mood|happy|sad|ok|okay|alright|stress|stressed|"
    r"emotion|emotional|lately|mental|depress|anxious|down|how is|how's)\b", re.I)


def _clip(text: str, limit: int = 320) -> str:
    """Up to ~2 sentences; if still too long, cut at a word boundary (never mid-word)."""
    s = " ".join(re.split(r"(?<=[.!?])\s+", text.strip())[:2]).strip()
    if len(s) <= limit:
        return s
    return s[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def compose_friend_answer(question: str, evidence: list[dict],
                          mood: str | None = None) -> str:
    """Deterministic, warm fallback answer when no model is reachable — grounded in
    the (already redacted) evidence, never inventing specifics."""
    if not evidence:
        return (f"I'm {COMPANION_NAME} — I know {OWNER_NAME} well, but I don't have "
                "much on that one. Ask me how he feels about something, or how he'd react.")
    # Lead with the most relevant memory's actual content so the reply tracks the
    # question (and varies with it), then tie in the next couple of related ones.
    top = evidence[0]
    detail = (top.get("content") or top.get("title") or "").strip()
    snippet = _clip(detail)
    others = [e["title"] for e in evidence[1:3]
              if e.get("title") and e["title"] != top.get("title")]
    bits = []
    mood_shown = bool(mood and _FEELING_RX.search(question or ""))
    if mood_shown:
        bits.append(f"Honestly, {OWNER_NAME}'s been in a fairly {mood} place lately.")
    if snippet:
        bits.append(f"On that — {snippet}" if mood_shown else snippet)
    elif top.get("title"):
        bits.append(f"What comes to mind for {OWNER_NAME} is {top['title']}.")
    if others:
        bits.append("It connects to " + " and ".join(others) + ".")
    return " ".join(bits)


# --- DB adapter -------------------------------------------------------------
def ask(db, question: str, use_llm: bool = True) -> dict:
    from sqlalchemy import select
    from .models import Memory
    from . import llm

    # Retrieve the memories most RELEVANT to the question via the pgvector
    # embeddings, so different questions surface different evidence. (Keyword
    # overlap alone returned the same recent rows for nearly every question —
    # friend questions rarely share words with memory titles — which made Jerry
    # repeat itself.) Falls back to recency if vector search is unavailable.
    # Quarantined / question rows are inert and must never reach an answer.
    from .embeddings import embed

    base = (
        select(Memory.source, Memory.title, Memory.content, Memory.meta)
        .where(Memory.source.notin_(("quarantine", "friend-question")))
    )
    rows = []
    try:
        qvec = embed(question)
        rows = db.execute(
            base.where(Memory.embedding.isnot(None))
            .order_by(Memory.embedding.cosine_distance(qvec)).limit(6)
        ).all()
    except Exception:
        rows = []
    if not rows:  # no embeddings / vector search unavailable → recent slice
        rows = db.execute(base.order_by(Memory.ts.desc()).limit(6)).all()
    evidence = redact_evidence(
        [{"source": s, "title": t, "content": c, "meta": m} for s, t, c, m in rows]
    )

    # Emotional read (qualitative).
    mood = None
    try:
        from . import emotional_cortex
        emo = emotional_cortex.build(db)
        if emo.get("ready"):
            mood = emo.get("mood")
    except Exception:
        pass

    answer, by = None, "deterministic"
    if use_llm and llm.available():
        persona = ""
        try:
            from . import persona as persona_mod
            persona = persona_mod.system_prompt(db)
        except Exception:
            pass
        system = friend_system_prompt(persona)
        ev_text = "\n".join(f"- {e['title']}: {e['content']}" for e in evidence)
        out = llm.complete(system, f"A friend asks: {question}\n\nWhat you know:\n{ev_text}",
                           temperature=0.6)
        if out:
            answer, by = out, "llm"
    if not answer:
        answer = compose_friend_answer(question, evidence, mood)

    return {
        "ready": True,
        "generated_at": _now().isoformat(),
        "question": question,
        "answer": answer,
        "generated_by": by,
        "discretion": "applied",   # raw records were redacted before answering
    }
