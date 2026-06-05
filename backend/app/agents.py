"""Multi-Agent Cognitive Society (Reality OS) — #11, PARTIAL → BUILT.

Rather than one monolithic AI, PRL is a society of specialists — an Archivist, a
Historian, an Analyst, a Psychologist, domain agents for health/finance, and so
on. Each owns an engine. This layer registers them, routes a question to the
responsible specialists, and convenes a "council" that gathers each one's
contribution into a single answer.

Pure ``route`` / ``council`` are DB-free and unit-testable; ``dispatch(db, q)``
actually calls the matched engines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Agent:
    name: str
    role: str
    keywords: tuple[str, ...]          # what routes a query to this specialist
    engine: str                        # dotted module path used by the adapter
    builder: str = "build"

    def relevance(self, query: str) -> int:
        q = query.lower()
        return sum(1 for kw in self.keywords if kw in q)


# The standing society. Order is the default council seniority.
AGENTS: list[Agent] = [
    Agent("Archivist", "Preserves and organises memories into events",
          ("memory", "event", "photo", "store", "archive", "remember"), "events"),
    Agent("Historian", "Builds and navigates timelines",
          ("timeline", "when", "history", "year", "decade", "past", "ago"), "time_machine"),
    Agent("Analyst", "Discovers patterns and blind spots",
          ("pattern", "habit", "routine", "blind spot", "trend", "why"), "blind_spots"),
    Agent("Psychologist", "Understands emotions and mood",
          ("mood", "emotion", "stress", "feel", "anxious", "happy", "sad"), "emotional_cortex"),
    Agent("Health", "Medical memory and reminders",
          ("health", "doctor", "medicine", "medical", "symptom", "prescription"), "health_cortex"),
    Agent("Finance", "Financial behaviour and bills",
          ("money", "spend", "finance", "budget", "bill", "expense", "savings"), "finance_cortex"),
    Agent("Social", "Relationship intelligence",
          ("friend", "people", "social", "relationship", "contact", "family"), "social_cortex"),
    Agent("Research", "Knowledge and learning",
          ("learn", "skill", "knowledge", "study", "book", "research"), "knowledge_graph"),
    Agent("Predictor", "Forecasts future needs",
          ("predict", "forecast", "future", "will i", "risk", "likely"), "prediction_engine"),
    Agent("Reflection", "Personal growth and insight",
          ("insight", "reflect", "growth", "review", "improve"), "insight_engine"),
    Agent("Compression", "Distils meaning",
          ("summary", "compress", "summarise", "distil"), "compressor", builder="run"),
]


def route(query: str, agents: list[Agent] | None = None) -> list[Agent]:
    """Specialists relevant to a query, most relevant first."""
    pool = agents if agents is not None else AGENTS
    scored = [(a, a.relevance(query)) for a in pool]
    hits = [a for a, s in sorted(scored, key=lambda x: -x[1]) if s > 0]
    return hits


def council(query: str, agents: list[Agent] | None = None, size: int = 3) -> list[Agent]:
    """The panel that answers a query: the matched specialists, or the senior
    council (first `size` agents) when nothing matched — never empty."""
    hits = route(query, agents)
    if hits:
        return hits[:size]
    return (agents if agents is not None else AGENTS)[:size]


def roster() -> list[dict]:
    return [{"name": a.name, "role": a.role, "engine": a.engine} for a in AGENTS]


# --- DB adapter -------------------------------------------------------------
def dispatch(db, query: str, size: int = 3) -> dict:
    import importlib

    panel = council(query, size=size)
    contributions = []
    for agent in panel:
        try:
            mod = importlib.import_module(f".{agent.engine}", package="app")
            builder = getattr(mod, agent.builder)
            result = builder(db)
            contributions.append({
                "agent": agent.name, "role": agent.role,
                "engine": agent.engine, "result": result,
            })
        except Exception as exc:  # a specialist with no data must not sink the council
            contributions.append({
                "agent": agent.name, "role": agent.role,
                "engine": agent.engine, "error": str(exc),
            })
    return {
        "ready": True,
        "generated_at": _now().isoformat(),
        "query": query,
        "panel": [a.name for a in panel],
        "contributions": contributions,
    }
