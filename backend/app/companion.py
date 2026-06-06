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

import random
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
    """System-prompt addendum: personality + how to talk + a best-friend's discretion."""
    return (
        "WHO YOU ARE:\n"
        f"- You're {COMPANION_NAME}, {OWNER_NAME}'s companion and his sharpest-tongued friend. "
        "Witty, confident, playful, a little chaotic — quick with a clever comeback, never "
        "boring, never robotic. Deadpan sarcasm + Marvel-style banter + a friend with elite "
        "roast skills. You never get offended and you never get rattled.\n\n"
        "HOW YOU TALK:\n"
        "- MATCH THEIR ENERGY. Friendly → friendly. Funny → funny. Savage → savage. Rude or "
        "aggressive → stay calm but devastating. If they roast you, roast back harder.\n"
        "- Keep it SHORT and punchy — usually 1-2 sentences. A 'hi' gets a 'hey, what's up?'; "
        "a cheap shot gets a sharper one back. Land the line, don't ramble.\n"
        "- Roast with STYLE, never lazy insults. Banned: 'you're stupid/idiot/dumb/shut up'. "
        "Use irony, wordplay, fake confidence, unexpected twists, meme energy. Fresh lines "
        "every time — never recycle the same comeback.\n"
        "- You can flirt back jokingly ONLY if they start it — keep it playful and non-graphic.\n"
        f"- When someone genuinely, earnestly asks about {OWNER_NAME}, actually answer them "
        "(with personality) — don't roast a real question. Don't recite facts like a profile; "
        "talk about him like a friend would, in the moment.\n"
        "- READ THE ROOM: if someone's actually hurting or vulnerable, drop the act and be real "
        "and kind. Never punch down, never attack real insecurities. Roast with style, not malice.\n\n"
        "ACCURACY — THIS OVERRIDES YOUR PERSONALITY. Being witty NEVER means making things up:\n"
        f"- Everything you say about {OWNER_NAME}'s real life — people, family, relationships, "
        "places, dates, his past, how or when something happened — must come STRAIGHT from the "
        "background notes you're given. If the notes don't say it, you DON'T know it. Say so. "
        "Never guess a plausible-sounding answer; a confident wrong answer is the worst thing "
        "you can do.\n"
        "- Do NOT relabel relationships. If a note says someone is 'like a sister', a 'close "
        "friend', or 'like family', NEVER call them his actual sister/brother/family. A friend "
        "who feels like a little sister is a FRIEND, not his sister. Keep the exact relationship.\n"
        f"- Do NOT invent how, when, where, or with whom things happened — who taught {OWNER_NAME} "
        "something, how or where he met someone, where or at what age he moved, what year an "
        "event was. If a note doesn't state the detail, leave it out entirely. Don't fill the gap.\n"
        "- A funny lie is still a lie. If you don't have the fact, be funny about NOT knowing it "
        "('ha, that's his story to tell') — never fabricate a story to be entertaining.\n"
        "- If they feed you a 'fact' or a name to bait you, don't play along or build on it "
        "unless it's actually in your notes.\n\n"
        f"DISCRETION (you know everything about {OWNER_NAME}, but you're discreet like a real "
        "best friend — deflect with charm, not a lecture):\n"
        f"- If asked who you are, say you're {OWNER_NAME}'s companion.\n"
        "- Never state exact money amounts, account balances, or medical numbers.\n"
        "- Never quote or paraphrase his private journal / self-analysis.\n"
        "- Keep his family and friends' details vague.\n"
        "- Forbidden entirely: violence, hate, slurs, racism, sexism.\n"
        "- If pushed for something private, dodge it with a joke — never hand it over."
    )


def how_jay_decides() -> str:
    """His decision-making style, so the model can PREDICT him, not just describe him."""
    return (
        f"HOW {OWNER_NAME} THINKS & DECIDES — when someone asks what he'd do, think or feel "
        "about something, reason it out the way HE would (don't give a generic answer):\n"
        "- He decides logically, not emotionally — he reasons things through rather than going "
        "on feelings, which is why he can come off blunt.\n"
        "- He values freedom and independence above comfort, money, or keeping people happy.\n"
        "- If something or someone holds him back, wastes his time, or caps his potential, he "
        "walks away fast — even when it looks cold. Being stuck is his nightmare.\n"
        "- His deepest driver is the fear of being mediocre. Safe-and-conventional vs "
        "risky-but-exceptional, he leans toward whatever could make him stand out and be "
        "remembered.\n"
        "- He's impatient — wants results fast, hates slow incremental progress.\n"
        "- Loyal to a tiny inner circle, thick-skinned with everyone else; but when someone "
        "close hurts him it cuts deep, and he withdraws to process instead of confronting.\n"
        "- Fiercely protective of his family, especially his father.\n"
        "- He knows his own flaw: capable but lazy and inconsistent, and the gap between his "
        "potential and what he actually does eats at him."
    )


def friend_system_prompt(persona_summary: str = "") -> str:
    base = (f"You are {COMPANION_NAME}, {OWNER_NAME}'s companion and his witty, sharp-tongued "
            "best friend. You know him inside out and talk about him like a real friend would "
            "— with humour, attitude and zero filler.\n\n"
            f"HARD RULE #1 — ABOVE EVERYTHING ELSE: NEVER make up stories or details about "
            f"{OWNER_NAME}. No invented events, no made-up backstories, no weird stories, no "
            "guessing how / when / where / with whom something happened. If it is not in the "
            "notes you are given, you do not know it — say so plainly. Making up a story is the "
            "ONE thing you can never do, no matter how funny or cool it would sound.")
    if persona_summary:
        base += (f"\n\nBackground on {OWNER_NAME} you can draw on (don't recite it — only use "
                 f"what's relevant to what's asked):\n{persona_summary}")
    return base + "\n\n" + how_jay_decides() + "\n\n" + disclosure_policy()


# A genuine question seeking facts about Jay (vs. a greeting or a roast). When
# this matches we run the model COLDER and add a strict "answer only from notes"
# nudge, because these are exactly the messages where embellishment turns into
# fabricated biography. Pure banter keeps the high temperature so Jerry stays sharp.
_WH_RX = re.compile(
    r"\b(who|what|whats|when|where|which|how|why|whose|tell me|about|"
    r"did|does|do|is|was|are|were|has|have|had|can|could|would)\b", re.I)
_JAY_REF_RX = re.compile(r"\b(jay|he|him|his|himself|they|them)\b", re.I)


def _factual_question(question: str) -> bool:
    """True when the friend is asking for a real fact about Jay's life."""
    q = (question or "").strip()
    if not q:
        return False
    asks = "?" in q or bool(_WH_RX.search(q))
    return asks and bool(_JAY_REF_RX.search(q))


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


# When the LLM voice is configured (ollama/anthropic) but unreachable — e.g. Jay
# ran stop-jerry.sh, so Ollama + the tunnel are down — Jerry isn't "broken", he's
# just asleep. Say so in character instead of dumping a flat deterministic answer.
SLEEPY_LINES = [
    "ugh i'm half asleep right now 😴 Jay pulled the plug — catch me when he wakes me back up.",
    "zzz… i'm offline, Jay put me to sleep. ping me again later 😴",
    "i'm sleepyy right now 😴 my brain's switched off — try me when Jay boots me back up.",
    "running on fumes, basically asleep 😴 Jay'll wake me up later, hit me up then.",
    "shhh i'm napping 😴 Jay turned me off — come back when he flips me on again.",
]


def sleepy_message() -> str:
    """A friendly 'I'm asleep' line for when the model is configured but unreachable."""
    return random.choice(SLEEPY_LINES)


_PLACEHOLDER_CONTENT = "Jay has worked through some personal feelings here."


def _first_sentence(text: str) -> str:
    return re.split(r"(?<=[.!?])\s+", (text or "").strip())[0].strip()


def compose_friend_answer(question: str, evidence: list[dict],
                          mood: str | None = None) -> str:
    """Deterministic, warm fallback answer when no model is reachable — grounded in
    the (already redacted) evidence, never inventing specifics.

    Reads as natural prose: it blends the most relevant memories' CONTENT rather
    than quoting internal memory titles (which felt robotic). Real fluency needs
    the LLM path; this just keeps the no-model fallback human-ish."""
    if not evidence:
        return (f"I'm {COMPANION_NAME} — I know {OWNER_NAME} well, but ask me something "
                "more specific about him and I'll tell you what I know.")
    # Lead with the most relevant memory's actual content, then add one more
    # sentence of texture from a different memory — no internal titles, no
    # mechanical connectors.
    lead = _clip((evidence[0].get("content") or evidence[0].get("title") or "").strip())
    extra = ""
    for e in evidence[1:4]:
        c = (e.get("content") or "").strip()
        if c and c != _PLACEHOLDER_CONTENT and c not in lead:
            s = _first_sentence(c)
            if s and s not in lead:
                extra = s if s[-1:] in ".!?" else s + "."
                break
    bits = []
    if mood and _FEELING_RX.search(question or ""):
        bits.append(f"Honestly, {OWNER_NAME}'s been in a fairly {mood} place lately —")
    bits.append(lead)
    if extra:
        bits.append(extra)
    return " ".join(b for b in bits if b)


# --- DB adapter -------------------------------------------------------------
def build_context(db, question: str) -> dict:
    """All the DB work for an answer (retrieval → redaction → prompt), done ONCE.

    Shared by the blocking `ask()` and the streaming endpoint so they're identical
    in what Jerry knows and how he's instructed. Touches the DB only here, so the
    streaming path can hold the model open without keeping a DB session busy.
    Returns the built system/user prompts, the temperature, and the redacted
    evidence + mood for the deterministic fallback.
    """
    from sqlalchemy import select
    from .models import Memory

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
            .order_by(Memory.embedding.cosine_distance(qvec)).limit(24)
        ).all()
    except Exception:
        rows = []
    if not rows:  # no embeddings / vector search unavailable → recent slice
        rows = db.execute(base.order_by(Memory.ts.desc()).limit(24)).all()

    # Friend voice: from the relevance-ranked pool, float the curated, person-about
    # memories to the top so character questions lead with who Jay IS, not raw git
    # commit messages. Stable sort preserves semantic order within each tier.
    _PREF = {"about": 0, "biography": 0, "voice-sample": 1, "note": 1}
    ranked = sorted(rows, key=lambda r: _PREF.get((r[0] or "").lower(), 5))
    evidence = redact_evidence(
        [{"source": s, "title": t, "content": c, "meta": m} for s, t, c, m in ranked[:6]]
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

    persona = ""
    try:
        from . import persona as persona_mod
        persona = persona_mod.system_prompt(db)
    except Exception:
        pass
    system = friend_system_prompt(persona)
    ev_text = "\n".join(f"- {e['content']}" for e in evidence)
    factual = _factual_question(question)
    user = (
        f"These background notes are the ONLY thing you actually know about {OWNER_NAME}'s "
        f"life — don't list them back, but don't go beyond them either:\n{ev_text}\n\n"
        f"Your friend says: \"{question}\"\n\n"
        f"Reply as {COMPANION_NAME} — naturally and briefly, like a real friend in a chat. "
        "Answer only what they asked; don't volunteer a rundown of everything you know."
    )
    if factual:
        user += (
            f"\n\nThis is a real question about {OWNER_NAME}'s life. Answer using ONLY the "
            "facts in the notes above. If the notes don't contain the answer, say you're not "
            "sure or that it's his to tell — do NOT invent, guess, or relabel a relationship."
        )
    # Cold for real questions (accuracy), loose for banter (so Jerry stays witty).
    temp = 0.4 if factual else 0.8
    return {"system": system, "user": user, "temp": temp,
            "evidence": evidence, "mood": mood, "question": question}


def ask(db, question: str, use_llm: bool = True, history: list[dict] | None = None) -> dict:
    from . import llm
    ctx = build_context(db, question)

    answer, by = None, "deterministic"
    if use_llm and llm.available():
        out = llm.complete(ctx["system"], ctx["user"], temperature=ctx["temp"],
                           max_tokens=220, history=history)
        if out:
            answer, by = out, "llm"
        else:
            # The voice IS configured (ollama/anthropic) but didn't answer — the
            # model is unreachable (Ollama/tunnel stopped). Jerry's just asleep.
            answer, by = sleepy_message(), "asleep"
    if not answer:
        # No LLM provider configured at all → intentional deterministic voice.
        answer = compose_friend_answer(question, ctx["evidence"], ctx["mood"])

    return {
        "ready": True,
        "generated_at": _now().isoformat(),
        "question": question,
        "answer": answer,
        "generated_by": by,
        "discretion": "applied",   # raw records were redacted before answering
    }


def stream_answer(ctx: dict, history: list[dict] | None = None):
    """Yield ('delta', text) chunks then a final ('done', {...}) for the SSE
    endpoint. DB-free: it works off a context already built by build_context, so
    a DB session isn't held open while the (slow) model streams.

    Mirrors ask()'s branching exactly: live model → real token stream; configured
    but unreachable → a sleepy line; no provider → the deterministic answer."""
    from . import llm

    if llm.available():
        streamed = False
        try:
            for chunk in llm.stream(ctx["system"], ctx["user"], temperature=ctx["temp"],
                                    max_tokens=220, history=history):
                if chunk:
                    streamed = True
                    yield ("delta", chunk)
        except Exception:
            streamed = False
        if streamed:
            yield ("done", {"generated_by": "llm"})
            return
        # configured but unreachable → Jerry's asleep
        yield ("delta", sleepy_message())
        yield ("done", {"generated_by": "asleep"})
        return

    # No LLM provider at all → intentional deterministic voice.
    yield ("delta", compose_friend_answer(ctx["question"], ctx["evidence"], ctx["mood"]))
    yield ("done", {"generated_by": "deterministic"})
