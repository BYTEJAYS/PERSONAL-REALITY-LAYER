"""Generative Reconstruction (Memory-Architecture V3).

The inverse of the compressor. The vision: PRL doesn't keep every byte forever —
it keeps enough (the Memory DNA) to *recreate* an experience on demand, the way
human imagination reconstructs a memory from its gist. This module expands a
compressed Memory-DNA record back into a rich, narrated recollection.

It is honest about what it is: reconstruction is generative, so every output is
labelled as such and a fidelity score states how faithfully the DNA supports it.
The LLM (when reachable) narrates; a deterministic, facts-only expansion is the
fallback. The pure core is unit-testable; `reconstruct(db, id)` reads the DNA the
compressor wrote into `meta`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional

CompleteFn = Callable[[str, str], Optional[str]]

DISCLAIMER = (
    "Reconstructed from compressed memory — a recreation of the experience from "
    "its preserved essence, not a literal record."
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _when(dna: dict) -> str:
    start = dna.get("start") or ""
    try:
        return f"{datetime.fromisoformat(start):%B %Y}"
    except (ValueError, TypeError):
        return "an earlier time"


def reconstruction_fidelity(dna: dict) -> float:
    """0..1 estimate of how faithfully the DNA supports a reconstruction — more
    preserved signal (summary, highlights, people, importance) → higher."""
    if not dna:
        return 0.0
    score = 0.2
    if dna.get("summary"):
        score += 0.2
    score += 0.1 * min(len(dna.get("highlights") or []), 3)
    score += 0.1 * min(len(dna.get("people") or []), 2)
    score += 0.2 * float(dna.get("importance", 0.0) or 0.0)
    return round(min(1.0, score), 3)


def deterministic_reconstruction(dna: dict) -> str:
    """Facts-only expansion — invents nothing beyond what the DNA preserved."""
    if not dna:
        return "No preserved essence remains for this memory."
    people = dna.get("people") or []
    highlights = dna.get("highlights") or []
    span = dna.get("span_days", 0)
    span_txt = "a single day" if not span else f"about {span} days"

    parts = [f"Around {_when(dna)}, over {span_txt},"]
    if dna.get("summary"):
        parts.append(dna["summary"])
    else:
        parts.append(f"there were {dna.get('size', 1)} connected moments.")
    if people:
        parts.append("It centred on " + ", ".join(people[:3]) + ".")
    if highlights:
        parts.append("What stayed: " + "; ".join(highlights[:3]) + ".")
    return " ".join(parts)


def llm_reconstruction(dna: dict, complete_fn: CompleteFn) -> Optional[str]:
    """Ask the model to vividly recreate the experience — strictly within the DNA."""
    system = (
        "You reconstruct a personal memory from its compressed essence. Write a "
        "warm, first-person recollection (3–5 sentences). Use ONLY the facts given "
        "— never invent specific names, numbers, or places that are not present. "
        "It is a reconstruction, not a transcript; keep it evocative but faithful."
    )
    user = (
        f"When: {_when(dna)}\n"
        f"Span (days): {dna.get('span_days', 0)}\n"
        f"People/themes: {', '.join(dna.get('people') or []) or 'n/a'}\n"
        f"Essence: {dna.get('summary') or 'n/a'}\n"
        f"What stayed: {'; '.join(dna.get('highlights') or []) or 'n/a'}"
    )
    text = complete_fn(system, user)
    return text.strip() if text else None


def reconstruct_memory(dna: dict, complete_fn: Optional[CompleteFn] = None) -> dict:
    """Return a labelled reconstruction with its fidelity. LLM-first, deterministic
    fallback — never fabricates beyond the preserved DNA."""
    by = "deterministic"
    narrative = None
    if complete_fn is not None:
        narrative = llm_reconstruction(dna, complete_fn)
        if narrative:
            by = "llm"
    if not narrative:
        narrative = deterministic_reconstruction(dna)
    return {
        "code": dna.get("code") if dna else None,
        "title": dna.get("title") if dna else None,
        "narrative": narrative,
        "generated_by": by,
        "fidelity": reconstruction_fidelity(dna),
        "is_reconstruction": True,
        "disclaimer": DISCLAIMER,
    }


# --- DB adapter -------------------------------------------------------------
def _complete_fn(use_llm: bool):
    from . import llm
    if use_llm and llm.available():
        return (lambda s, u: llm.complete(s, u, temperature=0.4)), True
    return None, False


def list_reconstructable(db, limit: int = 200) -> dict:
    from sqlalchemy import select
    from .models import Memory

    rows = db.execute(
        select(Memory.id, Memory.title, Memory.meta)
        .where(Memory.meta.has_key("compression"))  # noqa: W601 (SQLAlchemy JSONB op)
        .limit(limit)
    ).all()
    items = []
    for mid, title, meta in rows:
        dna = (meta or {}).get("compression", {}).get("dna", {})
        items.append({
            "memory_id": str(mid),
            "title": title,
            "code": dna.get("code"),
            "fidelity": reconstruction_fidelity(dna),
        })
    return {
        "generated_at": _now().isoformat(),
        "ready": len(items) > 0,
        "count": len(items),
        "reconstructable": items,
    }


def reconstruct(db, memory_id: str, use_llm: bool = True) -> dict:
    from .models import Memory

    m = db.get(Memory, memory_id)
    if m is None:
        return {"ready": False, "error": "memory not found"}
    dna = (m.meta or {}).get("compression", {}).get("dna")
    if not dna:
        return {"ready": False, "error": "memory has no compressed DNA to reconstruct"}

    fn, used = _complete_fn(use_llm)
    result = reconstruct_memory(dna, fn)
    return {
        "generated_at": _now().isoformat(),
        "ready": True,
        "memory_id": str(memory_id),
        "llm_used": used,
        **result,
    }
