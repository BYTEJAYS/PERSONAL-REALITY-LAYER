"""Semantic Compression Executor (Memory-Architecture V3).

The other V3 modules *detect* what should compress (events, aging, duplicates);
this one *executes* it. It turns a cluster of raw memories into one compact
representation — a short event summary plus a structured "Memory DNA" code — and
writes that back onto the store non-destructively (it tags rows in `meta`, never
deletes raw data; the aging policy decides actual raw expiry separately).

Design: the summary is produced by a pluggable `complete_fn` (the local LLM when
Ollama is up), with a deterministic, evidence-grounded summary as the fallback —
so compression runs whether or not a model is available, exactly like the rest of
PRL. The pure core (deterministic_summary / memory_dna / plan_compression) is
unit-testable; `run(db)` orchestrates and persists.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

# A model caller: (system, user) -> text or None when no model is reachable.
CompleteFn = Callable[[str, str], Optional[str]]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def deterministic_summary(event: dict) -> str:
    """Evidence-grounded summary built only from the event's own fields — no model,
    no invention. The honest fallback when no LLM is reachable."""
    people = event.get("people") or []
    highlights = event.get("highlights") or []
    span = event.get("span_days", 0)
    size = event.get("size", 1)

    span_txt = "a single day" if span == 0 else f"{span} days"
    base = f"{size} memories over {span_txt}"
    if people:
        base += " involving " + ", ".join(people[:3])
    if highlights:
        base += ": " + "; ".join(highlights[:3])
    return base + "."


def llm_summary(event: dict, complete_fn: CompleteFn) -> Optional[str]:
    """Ask the model to compress the cluster into one vivid sentence. Returns None
    if the model is unreachable (caller then uses the deterministic summary)."""
    system = (
        "You compress a cluster of one person's memories into a single vivid 1–2 "
        "sentence event summary. Preserve who, when, what, and emotional weight. "
        "Use only the facts given. No preamble, no lists."
    )
    user = (
        f"Title: {event.get('title', '')}\n"
        f"Span: {event.get('start', '')} → {event.get('end', '')} "
        f"({event.get('span_days', 0)} days)\n"
        f"People/themes: {', '.join(event.get('people') or []) or 'n/a'}\n"
        f"Memory count: {event.get('size', 1)}\n"
        f"Highlights: {'; '.join(event.get('highlights') or []) or 'n/a'}"
    )
    text = complete_fn(system, user)
    return text.strip() if text else None


def summarize_event(event: dict, complete_fn: Optional[CompleteFn] = None) -> tuple[str, str]:
    """Return (summary, generated_by). Prefers the LLM, falls back deterministically."""
    if complete_fn is not None:
        text = llm_summary(event, complete_fn)
        if text:
            return text, "llm"
    return deterministic_summary(event), "deterministic"


def memory_dna(event: dict, summary: str) -> dict:
    """The compact latent record the vision calls 'Memory DNA' — the minimum
    structured meaning needed to reconstruct the experience later."""
    start = event.get("start", "")
    people = event.get("people") or []
    code_seed = f"{start}|{','.join(people)}|{event.get('size', 1)}|{event.get('title', '')}"
    code = hashlib.sha1(code_seed.encode("utf-8")).hexdigest()[:12]
    return {
        "v": 1,
        "kind": "event",
        "code": code,
        "title": event.get("title", ""),
        "people": people,
        "start": start,
        "end": event.get("end", ""),
        "span_days": event.get("span_days", 0),
        "importance": event.get("importance", 0.5),
        "size": event.get("size", 1),
        "highlights": (event.get("highlights") or [])[:3],
        "summary": summary,
    }


@dataclass
class CompressionAction:
    kind: str                          # "event_summary" | "dedup_merge"
    anchor: str                        # master/anchor memory id (kept)
    absorbs: list[str] = field(default_factory=list)  # memories folded into the anchor
    summary: str = ""
    dna: dict = field(default_factory=dict)
    generated_by: str = "deterministic"

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "anchor": self.anchor,
            "absorbs": self.absorbs,
            "absorbed_count": len(self.absorbs),
            "summary": self.summary,
            "generated_by": self.generated_by,
            "dna_code": self.dna.get("code"),
        }


def plan_compression(
    events: list[dict],
    dup_groups: list[dict],
    complete_fn: Optional[CompleteFn] = None,
) -> list[CompressionAction]:
    """Decide the concrete compaction actions. Multi-memory events become one
    event-summary; duplicate groups merge redundant copies into their master."""
    actions: list[CompressionAction] = []

    for ev in events:
        ids = ev.get("memory_ids") or []
        if len(ids) <= 1:
            continue  # nothing to collapse
        anchor = ids[0]
        summary, by = summarize_event(ev, complete_fn)
        actions.append(CompressionAction(
            kind="event_summary",
            anchor=anchor,
            absorbs=ids[1:],
            summary=summary,
            dna=memory_dna(ev, summary),
            generated_by=by,
        ))

    for g in dup_groups:
        members = g.get("member_ids") or []
        if not members:
            continue
        actions.append(CompressionAction(
            kind="dedup_merge",
            anchor=g.get("master_id", ""),
            absorbs=members,
            summary=f"{len(members)} near-duplicate copies folded into master "
                    f"(avg sim {g.get('avg_similarity', 0)}).",
            generated_by="deterministic",
        ))

    return actions


def plan_stats(actions: list[CompressionAction], total_memories: int) -> dict:
    absorbed = sum(len(a.absorbs) for a in actions)
    return {
        "actions": len(actions),
        "event_summaries": sum(1 for a in actions if a.kind == "event_summary"),
        "dedup_merges": sum(1 for a in actions if a.kind == "dedup_merge"),
        "memories_absorbed": absorbed,
        # share of the store that collapses behind an anchor instead of standing alone
        "compaction_ratio": round(absorbed / total_memories, 3) if total_memories else 0.0,
    }


# --- DB adapter -------------------------------------------------------------
def _apply(db, actions: list[CompressionAction]) -> int:
    """Write compaction state into meta non-destructively. Returns rows touched."""
    from .models import Memory

    touched = 0
    now = _now().isoformat()
    for a in actions:
        anchor = db.get(Memory, a.anchor)
        if anchor is not None:
            anchor.meta = {
                **(anchor.meta or {}),
                "compression": {
                    "kind": a.kind,
                    "summary": a.summary,
                    "dna": a.dna,
                    "generated_by": a.generated_by,
                    "absorbed": a.absorbs,
                    "at": now,
                },
            }
            touched += 1
        for mid in a.absorbs:
            m = db.get(Memory, mid)
            if m is not None:
                key = "redundant_of" if a.kind == "dedup_merge" else "compressed_into"
                m.meta = {**(m.meta or {}), key: a.anchor}
                touched += 1
    db.commit()
    return touched


def run(db, dry_run: bool = True, use_llm: bool = True) -> dict:
    from . import dedup, events, memory_aging, llm

    ev = events.build(db)
    dup = dedup.build(db)
    aging = memory_aging.build(db)

    complete_fn: Optional[CompleteFn] = None
    llm_used = False
    if use_llm and llm.available():
        complete_fn = lambda s, u: llm.complete(s, u, temperature=0.2)  # noqa: E731
        llm_used = True

    actions = plan_compression(ev.get("events", []), dup.get("groups", []), complete_fn)
    total = ev.get("memories_in", 0)
    stats = plan_stats(actions, total)

    applied = 0
    if not dry_run:
        applied = _apply(db, actions)

    return {
        "generated_at": _now().isoformat(),
        "dry_run": dry_run,
        "llm_used": llm_used,
        "ready": len(actions) > 0,
        **stats,
        "rows_written": applied,
        "aging_due_for_compression": aging.get("due_for_compression", 0),
        "sample_actions": [a.as_dict() for a in actions[:25]],
    }
