"""Principle Engine — the persistent, evolving top of the Wisdom Cortex.

The Wisdom Engine *recomputes* lessons from current data each call. Principles
are different: they **persist and evolve**. A principle is a lesson that has been
seen enough to earn standing — it carries a confidence, an evidence count, a
first-seen date, a last-reinforced date, and a *history* of how its confidence
moved over time. As life adds evidence a principle **strengthens**; when the data
stops supporting it (or contradicts it) it **weakens**, then goes dormant — but is
never deleted, because how your beliefs changed is itself part of the record.

From the standing principles we distil **Personal Commandments** — the handful of
highest-conviction, most-evidenced principles you actually live by.

Persistence is migration-free: each principle is stored as a ``source='principle'``
memory whose ``meta['principle']`` holds the structured record (same pattern the
journal and life-cortexes use). The pure functions (``reconcile``, ``commandments``)
are DB-free and unit-tested; ``build(db)`` wires them to the store.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

PRINCIPLE_SOURCE = "principle"

# A principle only earns "active" standing once this many data points back it.
_ACTIVE_EVIDENCE = 3
# A material confidence move (worth recording a history snapshot for).
_DELTA = 0.05
# Only fade a principle that hasn't been reinforced for this long.
_FADE_AFTER_DAYS = 30
_FADE_FACTOR = 0.85


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _age_days(iso: str, now_iso: str) -> float:
    try:
        a = datetime.fromisoformat(iso)
        b = datetime.fromisoformat(now_iso)
        return (b - a).total_seconds() / 86400.0
    except (ValueError, TypeError):
        return 0.0


def reconcile(existing: list[dict], candidates: list[dict], now_iso: str) -> tuple[list[dict], list[dict]]:
    """Merge freshly-observed candidate principles into the standing set.

    `existing` and `candidates` are plain dicts keyed by a stable ``key``. Returns
    (principles, change_events). Candidates seen again are reinforced; standing
    principles no longer supported (and stale) fade. Nothing is dropped.
    """
    by_key = {e["key"]: e for e in existing if e.get("key")}
    seen: set[str] = set()
    out: list[dict] = []
    events: list[dict] = []

    for c in candidates:
        key = c.get("key")
        if not key:
            continue
        seen.add(key)
        ec = int(c.get("evidence_count", 1))
        conf = round(float(c.get("confidence", 0.5)), 3)
        prev = by_key.get(key)

        if prev is None:
            p = {
                "key": key,
                "statement": c["statement"],
                "category": c.get("category", "lesson"),
                "confidence": conf,
                "evidence_count": ec,
                "strength": round(float(c.get("strength", 0.5)), 3),
                "status": "active" if ec >= _ACTIVE_EVIDENCE else "forming",
                "exceptions": list(c.get("exceptions", [])),
                "sources": list(c.get("sources", [])),
                "first_seen": now_iso,
                "last_reinforced": now_iso,
                "history": [{"ts": now_iso, "confidence": conf, "evidence_count": ec, "event": "formed"}],
            }
            events.append({"key": key, "event": "formed", "statement": c["statement"]})
        else:
            old_conf = round(float(prev.get("confidence", conf)), 3)
            # Evidence only accumulates — never lose ground already earned.
            ec = max(int(prev.get("evidence_count", 1)), ec)
            history = list(prev.get("history", []))
            event = ("strengthened" if conf - old_conf >= _DELTA else
                     "weakened" if old_conf - conf >= _DELTA else None)
            if event:
                history.append({"ts": now_iso, "confidence": conf, "evidence_count": ec, "event": event})
                events.append({"key": key, "event": event, "statement": c["statement"],
                               "from": old_conf, "to": conf})
            p = {
                **prev,
                "statement": c["statement"],
                "category": c.get("category", prev.get("category", "lesson")),
                "confidence": conf,
                "evidence_count": ec,
                "strength": round(float(c.get("strength", prev.get("strength", 0.5))), 3),
                "status": "active" if ec >= _ACTIVE_EVIDENCE else "forming",
                "exceptions": list(c.get("exceptions") or prev.get("exceptions", [])),
                "sources": list(c.get("sources") or prev.get("sources", [])),
                "last_reinforced": now_iso,
                "history": history,
            }
        out.append(p)

    # Standing principles not supported this run: fade only if genuinely stale.
    for e in existing:
        key = e.get("key")
        if not key or key in seen:
            continue
        if _age_days(e.get("last_reinforced", now_iso), now_iso) < _FADE_AFTER_DAYS:
            out.append(e)  # recently reinforced — leave it be
            continue
        new_conf = round(float(e.get("confidence", 0.5)) * _FADE_FACTOR, 3)
        status = "dormant" if new_conf < 0.2 else "weakening"
        history = list(e.get("history", []))
        history.append({"ts": now_iso, "confidence": new_conf,
                        "evidence_count": e.get("evidence_count", 1), "event": "faded"})
        events.append({"key": key, "event": "faded", "statement": e.get("statement", "")})
        out.append({**e, "confidence": new_conf, "status": status, "history": history})

    return out, events


def _conviction(p: dict) -> float:
    """How much a principle has earned its place: confidence × evidence weight."""
    return float(p.get("confidence", 0.0)) * math.log2(2 + int(p.get("evidence_count", 1)))


def commandments(principles: list[dict], n: int = 10, max_per_category: int = 4) -> list[dict]:
    """The principles you actually live by: highest-conviction, category-diverse."""
    live = [p for p in principles
            if p.get("status") in ("active", "forming") and p.get("confidence", 0) >= 0.3]
    ranked = sorted(live, key=_conviction, reverse=True)
    out: list[dict] = []
    per_cat: dict[str, int] = {}
    for p in ranked:
        cat = p.get("category", "lesson")
        if per_cat.get(cat, 0) >= max_per_category:
            continue
        per_cat[cat] = per_cat.get(cat, 0) + 1
        out.append(p)
        if len(out) >= n:
            break
    return out


# --- DB adapter -------------------------------------------------------------
def _candidates_from_wisdom(wisdom: dict) -> list[dict]:
    out = []
    for w in (wisdom or {}).get("wisdom", []):
        if not w.get("key"):
            continue
        out.append({
            "key": w["key"], "statement": w["statement"], "category": w["category"],
            "confidence": w.get("confidence", 0.5), "strength": w.get("strength", 0.5),
            "evidence_count": w.get("evidence_count", 1),
            "exceptions": w.get("exceptions", []), "sources": w.get("sources", []),
        })
    return out


def build(db, persist: bool = True) -> dict:
    """Reconcile freshly-distilled wisdom into the standing principle set, persist
    the evolution, and surface the principles + your Personal Commandments."""
    from sqlalchemy import select

    from . import wisdom_engine
    from .memory_engine import MemoryInput, ingest
    from .models import Memory

    now = _now_iso()
    candidates = _candidates_from_wisdom(wisdom_engine.build(db))

    rows = db.execute(select(Memory).where(Memory.source == PRINCIPLE_SOURCE)).scalars().all()
    existing: list[dict] = []
    mem_by_key: dict[str, Memory] = {}
    for m in rows:
        p = (m.meta or {}).get("principle")
        if p and p.get("key"):
            existing.append(p)
            mem_by_key[p["key"]] = m

    principles, events = reconcile(existing, candidates, now)

    if persist:
        for p in principles:
            imp = round(min(1.0, float(p["confidence"]) * float(p["strength"])), 3)
            m = mem_by_key.get(p["key"])
            if m is None:
                ingest(db, MemoryInput(
                    ts=datetime.now(timezone.utc), source=PRINCIPLE_SOURCE,
                    title=p["statement"][:200], content=p["statement"],
                    importance=imp, memory_type="knowledge",
                    meta={"principle": p},
                ))
            else:
                nm = dict(m.meta or {})
                nm["principle"] = p
                m.meta = nm
                m.importance = imp
                m.title = p["statement"][:200]
                m.content = p["statement"]
                db.add(m)
        db.commit()

    ranked = sorted(principles, key=_conviction, reverse=True)
    cmds = commandments(principles)
    by_status: dict[str, int] = {}
    for p in principles:
        by_status[p["status"]] = by_status.get(p["status"], 0) + 1

    return {
        "generated_at": now,
        "ready": bool(principles),
        "note": "Principles earned from your own history — they strengthen as evidence "
                "accumulates and fade when it doesn't. Nothing here is invented.",
        "principle_count": len(principles),
        "status_counts": by_status,
        "commandments": [{"statement": p["statement"], "category": p["category"],
                          "confidence": p["confidence"], "evidence_count": p["evidence_count"]}
                         for p in cmds],
        "principles": [{k: p.get(k) for k in (
            "key", "statement", "category", "confidence", "evidence_count",
            "strength", "status", "exceptions", "first_seen", "last_reinforced", "history")}
            for p in ranked],
        "recent_changes": events[:12],
    }
