"""Free-text ingestion — the path for journals, brain-dumps, and reflections.

This is the connector for the *why*: the self-reflective text the you-model is
starving for. A pasted note becomes an embedded, retrievable memory, and we
mine it for two kinds of signal the git data never had:

- **Goals** — sentences like "I want to…", "my goal is…", "I'm trying to…".
  These create ``goal`` entities, which finally populate the long-empty goal
  region (and the Identity / Personal-OS engines that depend on it).
- **Skills / projects** — known tech (via ``extract_skills``) and any existing
  project entity named in the text get linked, so reflections enrich the twin.

Heuristic and conservative by design: it flags what it detected so nothing is
silently invented.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import select

from ..memory_engine import EntityRef, MemoryInput, ingest
from ..models import Entity
from .extract import extract_skills

# Sentence openers that signal an intention/goal. Captures the goal clause.
_GOAL_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bi want to\s+(.+)",
        r"\bi('?m| am) trying to\s+(.+)",
        r"\bmy goal is to\s+(.+)",
        r"\bmy goal is\s+(.+)",
        r"\bi('?d| would) like to\s+(.+)",
        r"\bi aim to\s+(.+)",
        r"\bi('?m| am) hoping to\s+(.+)",
        r"\bi plan to\s+(.+)",
        r"\bi need to\s+(.+)",
        r"\bi dream of\s+(.+)",
        r"\bi wish to\s+(.+)",
        r"\bi'?ll\s+(.+)",  # "I'll learn rust"
    )
]

_SENTENCE = re.compile(r"[.;\n!?]+")


def _clean_goal(clause: str) -> str:
    """Normalise a goal clause: drop a leading 'to', trailing filler, cap length."""
    clause = clause.strip().strip(",")
    clause = re.sub(r"^to\s+", "", clause, flags=re.IGNORECASE)
    clause = re.sub(r"\b(because|so that|since|but|and then)\b.*$", "", clause, flags=re.IGNORECASE).strip()
    return clause[:120]


def detect_goals(text: str) -> list[str]:
    """Extract distinct goal phrases from reflective text (conservative).

    One goal per sentence (first matching opener wins) so overlapping patterns
    on the same sentence can't produce near-duplicates.
    """
    found: list[str] = []
    seen: set[str] = set()
    for sentence in _SENTENCE.split(text):
        for rx in _GOAL_PATTERNS:
            m = rx.search(sentence)
            if not m:
                continue
            clause = _clean_goal(m.group(m.lastindex))
            key = clause.lower()
            # Skip false positives: quoted text (an example/error, not a real
            # intention) and negated clauses ("...— No").
            quoted = any(q in clause for q in ('"', "“", "”", "'"))
            negated = re.search(r"\bno\b|\bnot\b|n'?t\b", clause, re.IGNORECASE)
            if len(clause) >= 4 and key not in seen and not quoted and not negated:
                seen.add(key)
                found.append(clause)
            break  # one goal per sentence
    return found


def _title_from(text: str) -> str:
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "Note")
    return (first[:80] + "…") if len(first) > 80 else first


def ingest_text(
    db,
    text: str,
    *,
    ts: datetime | None = None,
    source: str = "note",
    title: str | None = None,
    importance: float = 0.6,
    emotion: str | None = None,
) -> dict:
    """Ingest one free-text reflection as a memory, mining goals + skills/projects."""
    text = (text or "").strip()
    if not text:
        return {"ok": False, "message": "Empty text — nothing to ingest."}

    ts = ts or datetime.now(timezone.utc)

    entities: list[EntityRef] = []
    skills = extract_skills(text)
    entities += [EntityRef("skill", s, role="reflected_on") for s in skills]

    # Link existing projects named in the text (case-insensitive substring).
    low = text.lower()
    project_names = db.execute(
        select(Entity.name).where(Entity.type == "project")
    ).scalars().all()
    linked_projects = [p for p in project_names if p and p.lower() in low]
    entities += [EntityRef("project", p, role="reflected_on") for p in linked_projects]

    goals = detect_goals(text)
    entities += [EntityRef("goal", g, role="stated") for g in goals]

    memory = ingest(
        db,
        MemoryInput(
            ts=ts, source=source, title=title or _title_from(text), content=text,
            importance=importance, emotion=emotion, entities=entities,
            meta={"ingest": "text", "goal_count": len(goals)},
        ),
    )
    return {
        "ok": True,
        "memory_id": str(memory.id) if memory else None,
        "skills_linked": skills,
        "projects_linked": linked_projects,
        "goals_detected": goals,
        "memory_type": memory.memory_type if memory else None,
    }
