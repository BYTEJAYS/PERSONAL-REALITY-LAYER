"""AI Chat query engine.

Turns a natural-language question into an answer grounded in the user's actual
memories. It detects intent, retrieves the relevant evidence from Postgres
(vector + structured filters), composes a deterministic answer, and — when a
local/cloud LLM is reachable — has the model phrase that same grounded evidence
more naturally. Every answer carries its citations.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone

from dateutil import parser as dateparser
from dateutil.relativedelta import relativedelta
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from . import llm, persona
from .embeddings import embed
from .models import Entity, Memory, MemoryEntity


@dataclass
class Citation:
    id: str
    ts: str
    source: str
    title: str


@dataclass
class Answer:
    answer: str
    intent: str
    citations: list[Citation] = field(default_factory=list)
    data: dict = field(default_factory=dict)
    llm_used: bool = False
    # Raw memory rows the handler actually used — internal, fed to the LLM so it
    # reasons over real content (not just the deterministic summary). Not serialized.
    sources: list = field(default_factory=list)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _cite(m: Memory) -> Citation:
    return Citation(id=str(m.id), ts=m.ts.isoformat(), source=m.source, title=m.title)


# --- date understanding -----------------------------------------------------
def _day_bounds(d: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(d, time.min, tzinfo=timezone.utc),
        datetime.combine(d, time.max, tzinfo=timezone.utc),
    )


def _resolve_date(text: str, today: date) -> date | None:
    t = text.lower()
    if "yesterday" in t:
        return today - timedelta(days=1)
    if "today" in t:
        return today
    # Explicit date like "March 12" / "2026-03-12" / "12 Aug".
    m = re.search(
        r"\b(\d{4}-\d{1,2}-\d{1,2}|\d{1,2}(st|nd|rd|th)?\s+\w+|\w+\s+\d{1,2}(st|nd|rd|th)?)\b", t
    )
    if m:
        try:
            return dateparser.parse(m.group(0), default=datetime(today.year, 1, 1)).date()
        except (ValueError, OverflowError):
            return None
    return None


def _resolve_window(text: str, today: date) -> tuple[datetime, datetime, str]:
    t = text.lower()
    end = datetime.combine(today, time.max, tzinfo=timezone.utc)
    if "last month" in t or "past month" in t:
        start = end - relativedelta(months=1)
        return start, end, "the last month"
    if "last week" in t or "past week" in t:
        start = end - timedelta(days=7)
        return start, end, "the last week"
    if "last year" in t or "past year" in t:
        start = end - relativedelta(years=1)
        return start, end, "the last year"
    start = end - relativedelta(months=1)
    return start, end, "recently"


# --- intent classification --------------------------------------------------
def classify(message: str) -> str:
    m = message.lower()
    if re.search(r"\b(where was i|where did i go|where have i been)\b", m):
        return "location_day"
    if re.search(r"\b(neglect|abandon|ignor|haven't (touched|worked)|forgotten|forget)", m):
        return "neglect"
    if re.search(r"\b(when did i (first|start)|first (become|get) interested|first learn)\b", m):
        return "first_interest"
    if re.search(r"\b(most (time|of my time)|spend|spent|consumed|busiest|focus)\b", m):
        return "time_spent"
    if re.search(r"\b(what did i do|what was i doing|summary|recap)\b", m):
        return "day_recap"
    return "semantic"


# --- handlers ---------------------------------------------------------------
def _memories_on(db: Session, d: date) -> list[Memory]:
    lo, hi = _day_bounds(d)
    return list(
        db.execute(
            select(Memory).options(selectinload(Memory.links))
            .where(Memory.ts >= lo, Memory.ts <= hi).order_by(Memory.ts.asc())
        ).scalars().all()
    )


def _handle_day(db: Session, message: str, today: date, intent: str) -> Answer:
    d = _resolve_date(message, today) or (today - timedelta(days=1))
    rows = _memories_on(db, d)
    if not rows:
        return Answer(f"I have no recorded memories for {d.strftime('%B %d, %Y')}.", intent)

    projects: Counter = Counter()
    people: Counter = Counter()
    skills: Counter = Counter()
    for m in rows:
        for link in m.links:
            bucket = {"project": projects, "person": people, "skill": skills}.get(link.entity.type)
            if bucket is not None:
                bucket[link.entity.name] += 1

    bits = [f"On {d.strftime('%B %d, %Y')} you have {len(rows)} recorded memories."]
    if projects:
        bits.append("Projects: " + ", ".join(n for n, _ in projects.most_common(3)) + ".")
    if skills:
        bits.append("You applied " + ", ".join(n for n, _ in skills.most_common(4)) + ".")
    if people:
        bits.append("People: " + ", ".join(n for n, _ in people.most_common(5)) + ".")
    return Answer(
        " ".join(bits), intent,
        citations=[_cite(m) for m in rows[:8]],
        data={"date": d.isoformat(), "count": len(rows),
              "projects": projects.most_common(5), "skills": skills.most_common(5)},
        sources=rows[:8],
    )


def _handle_time_spent(db: Session, message: str, today: date) -> Answer:
    start, end, label = _resolve_window(message, today)
    rows = db.execute(
        select(Entity.name, func.count(MemoryEntity.memory_id), func.sum(Memory.importance))
        .join(MemoryEntity, MemoryEntity.entity_id == Entity.id)
        .join(Memory, Memory.id == MemoryEntity.memory_id)
        .where(Entity.type == "project", Memory.ts >= start, Memory.ts <= end)
        .group_by(Entity.name)
        .order_by(func.sum(Memory.importance).desc())
    ).all()
    if not rows:
        return Answer(f"I don't see any project activity in {label}.", "time_spent")
    top = rows[0]
    ranking = ", ".join(f"{n} ({c})" for n, c, _ in rows[:5])
    return Answer(
        f"In {label}, your most active project was {top[0]} ({top[1]} memories). "
        f"Full ranking by effort: {ranking}.",
        "time_spent",
        data={"window": label, "ranking": [[n, c] for n, c, _ in rows[:8]]},
    )


def _handle_neglect(db: Session, today: date) -> Answer:
    cutoff = _now() - timedelta(days=21)
    rows = db.execute(
        select(Entity.name, func.max(Memory.ts), Entity.weight)
        .join(MemoryEntity, MemoryEntity.entity_id == Entity.id)
        .join(Memory, Memory.id == MemoryEntity.memory_id)
        .where(Entity.type == "project")
        .group_by(Entity.id)
        .having(func.max(Memory.ts) < cutoff)
        .order_by(Entity.weight.desc())
    ).all()
    if not rows:
        return Answer("Nothing looks neglected — every project has activity in the last 3 weeks.", "neglect")
    items = [f"{n} (last touched {ts.strftime('%b %d')})" for n, ts, _ in rows[:5]]
    return Answer(
        "Projects you may be neglecting: " + "; ".join(items) + ".",
        "neglect",
        data={"neglected": [[n, ts.isoformat()] for n, ts, _ in rows]},
    )


def _handle_first_interest(db: Session, message: str) -> Answer:
    topic = re.sub(
        r".*\b(interested in|first learn(ed)?|start(ed)? (with|using|learning)|first)\b", "", message,
        flags=re.IGNORECASE,
    ).strip(" ?.") or message
    vec = embed(topic)
    rows = db.execute(
        select(Memory).options(selectinload(Memory.links))
        .order_by(Memory.embedding.cosine_distance(vec)).limit(25)
    ).scalars().all()
    if not rows:
        return Answer(f"I couldn't find anything related to “{topic}”.", "first_interest")
    earliest = min(rows, key=lambda m: m.ts)
    return Answer(
        f"The earliest memory related to “{topic}” is from {earliest.ts.strftime('%B %d, %Y')}: "
        f"“{earliest.title}”.",
        "first_interest", citations=[_cite(earliest)],
        data={"topic": topic, "first_ts": earliest.ts.isoformat()},
        sources=[earliest] + [m for m in rows[:5] if m is not earliest],
    )


def _handle_semantic(db: Session, message: str) -> Answer:
    vec = embed(message)
    rows = db.execute(
        select(Memory).options(selectinload(Memory.links))
        .order_by(Memory.embedding.cosine_distance(vec)).limit(8)
    ).scalars().all()
    if not rows:
        return Answer("I don't have any memories that match that yet.", "semantic")
    lines = [f"• {m.title} ({m.ts.strftime('%b %d, %Y')})" for m in rows[:5]]
    return Answer(
        "Here's what I found related to your question:\n" + "\n".join(lines),
        "semantic", citations=[_cite(m) for m in rows],
        sources=rows,
    )


# --- grounded reasoning -----------------------------------------------------
def _entity_tag(m: Memory) -> str:
    names = [link.entity.name for link in m.links][:6]
    return f" [{', '.join(names)}]" if names else ""


def _evidence_block(sources: list[Memory]) -> str:
    """Render raw memory content the LLM can actually reason over (not just titles)."""
    out = []
    for i, m in enumerate(sources, 1):
        body = (m.content or "").strip().replace("\n", " ")
        if len(body) > 600:
            body = body[:600] + "…"
        out.append(
            f"[{i}] {m.ts.strftime('%Y-%m-%d')} · {m.source} · {m.title}{_entity_tag(m)}"
            + (f"\n    {body}" if body else "")
        )
    return "\n".join(out)


def _reason(
    db: Session, message: str, ans: Answer, history: list[dict] | None
) -> None:
    """If a model is reachable, have it reason over raw evidence in the user's voice.

    Mutates `ans` in place. The deterministic answer (ans.answer) survives as the
    fallback if no model is available or the call fails.
    """
    if not llm.available():
        return

    # Ensure the model has real content to reason over even for aggregate intents
    # (time_spent / neglect retrieve no raw rows of their own).
    sources = ans.sources or _retrieve(db, message, k=8)

    parts = []
    if history:
        convo = "\n".join(
            f"{h.get('role', 'user')}: {h.get('content', '')}" for h in history[-6:]
        )
        parts.append("Recent conversation:\n" + convo)
    parts.append(f"Their question: {message}")
    if ans.data:
        parts.append(f"Pre-computed facts: {ans.data}")
    if sources:
        parts.append("Evidence from their memories:\n" + _evidence_block(sources))
    else:
        parts.append("Evidence from their memories: (none found)")
    parts.append(
        "Answer their question grounded ONLY in the evidence above. Cite the memories "
        "you used by their date/title. If the evidence doesn't support an answer, say so."
    )

    phrased = llm.complete(persona.system_prompt(db), "\n\n".join(parts))
    if phrased:
        ans.answer = phrased
        ans.llm_used = True
        if sources and not ans.citations:
            ans.citations = [_cite(m) for m in sources]


def _retrieve(db: Session, message: str, k: int = 8) -> list[Memory]:
    vec = embed(message)
    return list(
        db.execute(
            select(Memory).options(selectinload(Memory.links))
            .order_by(Memory.embedding.cosine_distance(vec)).limit(k)
        ).scalars().all()
    )


# --- public entrypoint ------------------------------------------------------
def ask(
    db: Session,
    message: str,
    today: date | None = None,
    history: list[dict] | None = None,
) -> Answer:
    today = today or _now().date()
    intent = classify(message)

    if intent in ("location_day", "day_recap"):
        ans = _handle_day(db, message, today, intent)
    elif intent == "time_spent":
        ans = _handle_time_spent(db, message, today)
    elif intent == "neglect":
        ans = _handle_neglect(db, today)
    elif intent == "first_interest":
        ans = _handle_first_interest(db, message)
    else:
        ans = _handle_semantic(db, message)

    _reason(db, message, ans, history)
    return ans
