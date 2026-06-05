"""Reality Compiler (Reality OS) — the heart of PRL.

A traditional compiler lowers source code through intermediate representations to
machine instructions. The Reality Compiler lowers *life* through stages —
raw → features → entities → events → patterns → knowledge → meaning → wisdom —
each one a larger reduction of redundancy into understanding. Everything PRL knows
passes through this pipeline; the existing engines are its stages.

Pure ``pipeline_report`` computes the stage-to-stage reductions and is
unit-testable; ``compile(db)`` runs the real engines to populate the counts.
"""

from __future__ import annotations

from datetime import datetime, timezone

# Ordered IR stages, coarsest understanding last.
STAGES = ("raw", "features", "entities", "events", "patterns",
          "knowledge", "meaning", "wisdom")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def pipeline_report(stage_counts: dict) -> dict:
    """Given a count per stage, report each stage's size, the reduction from the
    previous stage, and the overall raw→wisdom compaction."""
    stages = []
    prev = None
    for name in STAGES:
        count = max(0, int(stage_counts.get(name, 0)))
        reduction = None
        if prev is not None and prev > 0:
            reduction = round(1 - count / prev, 3)
        stages.append({"stage": name, "count": count, "reduction_from_prev": reduction})
        prev = count

    raw = stage_counts.get("raw", 0)
    wisdom = stage_counts.get("wisdom", 0)
    overall = round(1 - wisdom / raw, 4) if raw > 0 else 0.0
    return {
        "stages": stages,
        "raw": raw,
        "wisdom": wisdom,
        "overall_compaction": overall,   # fraction of raw volume distilled away
    }


# --- DB adapter -------------------------------------------------------------
def _safe(fn, default=0):
    try:
        return fn()
    except Exception:  # an engine needing data we lack must not break the compile
        return default


def compile(db) -> dict:
    from sqlalchemy import func, select
    from .models import Entity, Memory
    from . import (events, patterns, knowledge_graph, compressor, insight_engine,
                   blind_spots)

    raw = _safe(lambda: db.execute(select(func.count(Memory.id))).scalar() or 0)
    if not raw:
        return {"ready": False, "message": "Nothing to compile yet."}

    features = _safe(lambda: db.execute(
        select(func.count(Memory.id)).where(Memory.embedding.isnot(None))).scalar() or 0)
    entities = _safe(lambda: db.execute(select(func.count(Entity.id))).scalar() or 0)

    ev = _safe(lambda: events.build(db), {})
    events_n = ev.get("events_out", 0) if isinstance(ev, dict) else 0

    pat = _safe(lambda: patterns.build(db), {})
    patterns_n = pat.get("stored_units", 0) if isinstance(pat, dict) else 0

    kg = _safe(lambda: knowledge_graph.build(db), {})
    knowledge_n = len(kg.get("nodes", [])) if isinstance(kg, dict) else 0

    comp = _safe(lambda: compressor.run(db, dry_run=True, use_llm=False), {})
    meaning_n = comp.get("actions", 0) if isinstance(comp, dict) else 0

    ins = _safe(lambda: insight_engine.build(db) if hasattr(insight_engine, "build") else {}, {})
    insight_n = len(ins.get("insights", [])) if isinstance(ins, dict) else 0
    bs = _safe(lambda: blind_spots.build(db), {})
    blind_n = len(bs.get("blind_spots", [])) if isinstance(bs, dict) else 0
    wisdom_n = insight_n + blind_n

    counts = {
        "raw": raw,
        "features": features,
        "entities": entities,
        "events": events_n,
        "patterns": patterns_n,
        "knowledge": knowledge_n,
        "meaning": meaning_n,
        "wisdom": wisdom_n,
    }
    report = pipeline_report(counts)
    return {
        "ready": True,
        "generated_at": _now().isoformat(),
        **report,
    }
