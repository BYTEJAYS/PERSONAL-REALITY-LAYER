"""Guided Self-Intake (Reality OS) — how the owner feeds the model.

A biography alone is a highlight reel. What personalises the model is honest,
reflective, first-person input about *how you think and react*. This module
provides a high-signal prompt set and ingests each answer through the text path
with the right `source` so it lands in the engines that build "you": reflections
feed `self_model` / `you_model`, voice samples feed the persona, life facts seed
the graph.

`PROMPTS` / `prompt_set` are pure and unit-testable; `ingest_answer` persists.
Owner-only (gated in the router) — this is how *you* train it, not friends.
"""

from __future__ import annotations

from datetime import datetime, timezone

# Each prompt routes to a source the right engine reads. reflection → self/you
# model; voice-sample → persona style; biography/people → memory + graph.
PROMPTS: list[dict] = [
    {"id": "values", "category": "Values",
     "prompt": "What are your core values? Name 3–5, and for each, a real moment it showed up.",
     "source": "reflection", "importance": 0.9},
    {"id": "formative", "category": "Formative moments",
     "prompt": "What moments shaped who you are — and what did each teach you?",
     "source": "reflection", "importance": 0.85},
    {"id": "decisions", "category": "How you decide",
     "prompt": "Describe a big decision you made and the actual reasoning behind it.",
     "source": "reflection", "importance": 0.9},
    {"id": "stress", "category": "Under pressure",
     "prompt": "How do you react under stress? Walk through a real example, honestly.",
     "source": "reflection", "importance": 0.85},
    {"id": "conflict", "category": "Conflict & trust",
     "prompt": "How do you handle conflict, or being let down by someone you trusted?",
     "source": "reflection", "importance": 0.8},
    {"id": "failure", "category": "Failure",
     "prompt": "How do you deal with failure? A real instance, and what you did after.",
     "source": "reflection", "importance": 0.8},
    {"id": "money", "category": "Money",
     "prompt": "What's your relationship with money — how do you think about spending vs saving?",
     "source": "reflection", "importance": 0.7},
    {"id": "people", "category": "Your people",
     "prompt": "Who matters most to you, and what does each of them mean to you?",
     "source": "reflection", "importance": 0.8},
    {"id": "opinions", "category": "Strong opinions",
     "prompt": "Things you'd argue about — opinions you hold strongly and why.",
     "source": "reflection", "importance": 0.7},
    {"id": "voice", "category": "Your voice",
     "prompt": "Your humour, your quirks, how you actually text. Paste a few real messages if you can.",
     "source": "voice-sample", "importance": 0.7},
    {"id": "dreams", "category": "Where you're going",
     "prompt": "Where do you want your life to go? Ambitions, the bucket list, the dream.",
     "source": "reflection", "importance": 0.85},
    {"id": "bio", "category": "Your story",
     "prompt": "Tell your life story so far, in your own words — the spine of it.",
     "source": "biography", "importance": 0.8},
]

_BY_ID = {p["id"]: p for p in PROMPTS}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def prompt_set() -> dict:
    """The full intake questionnaire."""
    return {
        "count": len(PROMPTS),
        "guidance": ("Answer in your own honest, first-person words — small dated "
                     "entries beat one polished essay. The reflective ones (how you "
                     "decide, react, what you value) personalise it most."),
        "prompts": PROMPTS,
    }


# --- DB adapter -------------------------------------------------------------
def ingest_answer(db, prompt_id: str, text: str) -> dict:
    from .ingestion.text_ingest import ingest_text

    prompt = _BY_ID.get(prompt_id)
    if prompt is None:
        return {"ready": False, "error": f"unknown prompt: {prompt_id}"}
    if not (text or "").strip():
        return {"ready": False, "error": "empty answer"}

    res = ingest_text(
        db, text,
        source=prompt["source"],
        title=f"Intake · {prompt['category']}",
        importance=prompt["importance"],
    )
    return {
        "ready": True,
        "generated_at": _now().isoformat(),
        "prompt_id": prompt_id,
        "category": prompt["category"],
        "stored_as": prompt["source"],
        **res,
    }


def ingest_bio(db, text: str) -> dict:
    from .ingestion.text_ingest import ingest_text

    if not (text or "").strip():
        return {"ready": False, "error": "empty biography"}
    res = ingest_text(db, text, source="biography",
                      title="Intake · Your story", importance=0.8)
    return {"ready": True, "generated_at": _now().isoformat(), "stored_as": "biography", **res}
