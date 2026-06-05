"""Source Attribution Layer (Reality OS) — #4, PARTIAL → BUILT.

Every fact in PRL must answer "where did this come from?". This layer assembles a
memory's provenance: the sources behind it, ordered into a chain, whether it is
auditable (independently corroborated), and a plain-language audit trail. It reuses
the Confidence Engine's source-quality scale so trust and provenance agree.

Pure ``build_provenance`` / ``audit_trail`` are DB-free and unit-testable;
``build(db, id)`` assembles one memory's provenance and ``coverage(db)`` reports
how auditable the whole store is.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .confidence_engine import source_quality


def _now() -> datetime:
    return datetime.now(timezone.utc)


def build_provenance(sources: list[dict]) -> dict:
    """`sources` = [{"type": str, "ref": str, "ts": iso|None}]. Returns the
    provenance record: ordered chain, distinct types, auditability, quality."""
    clean = [s for s in sources if s.get("type")]
    if not clean:
        return {"sources": [], "distinct_types": 0, "auditable": False,
                "quality": 0.0, "summary": "No recorded source."}

    chain = sorted(clean, key=lambda s: s.get("ts") or "")
    types = [s["type"].strip().lower() for s in clean]
    distinct = sorted(set(types))
    quality = round(max(source_quality(t) for t in types), 3)
    # Auditable when at least two independent source types back it.
    auditable = len(distinct) >= 2

    label = " + ".join(distinct[:4])
    plural = "sources" if len(clean) != 1 else "source"
    summary = f"Known from {label} ({len(clean)} {plural})."
    return {
        "sources": chain,
        "distinct_types": len(distinct),
        "types": distinct,
        "auditable": auditable,
        "quality": quality,
        "summary": summary,
    }


def audit_trail(provenance: dict) -> str:
    """One human-readable line tracing where a memory came from."""
    if not provenance.get("sources"):
        return "No provenance on record — this memory is unsourced."
    steps = []
    for s in provenance["sources"]:
        when = (s.get("ts") or "")[:10]
        ref = s.get("ref") or s["type"]
        steps.append(f"{s['type']}({ref}{', ' + when if when else ''})")
    verdict = "auditable" if provenance.get("auditable") else "single-source"
    return " ← ".join(steps) + f"  [{verdict}]"


def _sources_for(memory_id, source, meta, ts) -> list[dict]:
    out = []
    if source:
        out.append({"type": source, "ref": str(memory_id), "ts": ts.isoformat() if ts else None})
    for s in (meta or {}).get("sources", []):
        out.append({"type": s, "ref": "linked", "ts": ts.isoformat() if ts else None})
    if (meta or {}).get("finance"):
        out.append({"type": "transaction", "ref": "finance-record", "ts": ts.isoformat() if ts else None})
    if (meta or {}).get("health"):
        out.append({"type": "health", "ref": "health-record", "ts": ts.isoformat() if ts else None})
    return out


# --- DB adapter -------------------------------------------------------------
def build(db, memory_id: str) -> dict:
    from .models import Memory

    m = db.get(Memory, memory_id)
    if m is None:
        return {"ready": False, "error": "memory not found"}
    prov = build_provenance(_sources_for(m.id, m.source, m.meta, m.ts))
    return {
        "ready": True,
        "generated_at": _now().isoformat(),
        "memory_id": str(memory_id),
        "title": m.title,
        "provenance": prov,
        "audit_trail": audit_trail(prov),
    }


def coverage(db) -> dict:
    """How auditable the whole store is: share of memories with 1 / 2+ sources."""
    from sqlalchemy import select
    from .models import Memory

    rows = db.execute(select(Memory.id, Memory.source, Memory.meta, Memory.ts)).all()
    if not rows:
        return {"ready": False, "message": "No memories yet."}
    sourced = auditable = 0
    for mid, source, meta, ts in rows:
        prov = build_provenance(_sources_for(mid, source, meta, ts))
        if prov["sources"]:
            sourced += 1
        if prov["auditable"]:
            auditable += 1
    n = len(rows)
    return {
        "ready": True,
        "generated_at": _now().isoformat(),
        "memories": n,
        "sourced_share": round(sourced / n, 3),
        "auditable_share": round(auditable / n, 3),
    }
