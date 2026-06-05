"""Confidence Engine + Reality Integrity (Reality OS).

Every fact in PRL carries how much we should trust it. Confidence blends how many
independent sources corroborate it, how good those sources are, whether it was
verified, and how reliable its timestamp is. Low-confidence claims are
*quarantined* — they never enter long-term storage as truth — which is how PRL
guards against hallucinated memories.

Pure ``score_confidence`` is DB-free and unit-testable; ``build(db)`` reads each
memory's provenance from its source + metadata.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone

# Source trust per provenance type (0..1).
SOURCE_QUALITY = {
    "invoice": 0.95, "bank": 0.95, "transaction": 0.9, "document": 0.85,
    "calendar": 0.8, "email": 0.75, "photo": 0.7, "video": 0.7,
    "git": 0.85, "wearable": 0.8, "health": 0.85,
    "chat": 0.55, "whatsapp": 0.55, "sms": 0.55, "note": 0.5,
    "self-analysis": 0.5, "journal": 0.5, "text": 0.5, "browser": 0.5,
    "inferred": 0.3, "unknown": 0.3,
}
QUARANTINE_THRESHOLD = 0.35   # below this a claim is not trusted into long-term store


def _now() -> datetime:
    return datetime.now(timezone.utc)


def source_quality(source: str) -> float:
    return SOURCE_QUALITY.get((source or "unknown").strip().lower(), 0.4)


@dataclass
class Evidence:
    sources: list[str] = field(default_factory=list)  # provenance types
    verified: bool = False                            # cross-checked against another source
    timestamp_reliable: bool = True                   # is the time trustworthy

    @property
    def count(self) -> int:
        return len(self.sources)

    @property
    def distinct(self) -> int:
        return len(set(s.strip().lower() for s in self.sources))


def score_confidence(ev: Evidence) -> dict:
    if ev.count == 0:
        return {"confidence": 0.0, "label": "unverified", "quarantine": True,
                "reasons": ["no sources"], "evidence_count": 0}

    best = max(source_quality(s) for s in ev.sources)
    # Each extra *distinct* corroborating source closes part of the gap to 1.0.
    corroboration = 1.0 - (1.0 - best)
    for _ in range(ev.distinct - 1):
        corroboration = 1.0 - (1.0 - corroboration) * 0.5
    conf = corroboration
    if ev.verified:
        conf = 1.0 - (1.0 - conf) * 0.5
    if not ev.timestamp_reliable:
        conf *= 0.9
    conf = round(min(1.0, conf), 3)

    reasons = [f"{ev.distinct} distinct source(s)",
               f"best source quality {round(best, 2)}"]
    if ev.verified:
        reasons.append("cross-verified")
    if not ev.timestamp_reliable:
        reasons.append("uncertain timestamp")

    label = ("high" if conf >= 0.8 else "medium" if conf >= 0.55
             else "low" if conf >= QUARANTINE_THRESHOLD else "unverified")
    return {
        "confidence": conf,
        "label": label,
        "quarantine": conf < QUARANTINE_THRESHOLD,
        "evidence_count": ev.count,
        "distinct_sources": ev.distinct,
        "reasons": reasons,
    }


# --- DB adapter -------------------------------------------------------------
def build(db) -> dict:
    from sqlalchemy import select
    from .models import Memory

    rows = db.execute(select(Memory.id, Memory.source, Memory.meta, Memory.ts)).all()
    if not rows:
        return {"ready": False, "message": "No memories to assess yet."}

    dist = Counter()
    quarantined = []
    scored = []
    for mid, source, meta, ts in rows:
        meta = meta or {}
        # Provenance = the row's source + any extra sources the miners recorded.
        sources = [source] + list(meta.get("sources", []))
        if meta.get("finance"):
            sources.append("transaction")
        if meta.get("health"):
            sources.append("health")
        ev = Evidence(
            sources=[s for s in sources if s],
            verified=bool(meta.get("verified") or ev_distinct(sources) >= 2),
            timestamp_reliable=ts is not None,
        )
        res = score_confidence(ev)
        dist[res["label"]] += 1
        scored.append((str(mid), res))
        if res["quarantine"]:
            quarantined.append({"memory_id": str(mid), **res})

    return {
        "ready": True,
        "generated_at": _now().isoformat(),
        "assessed": len(rows),
        "distribution": dict(dist),
        "quarantine_threshold": QUARANTINE_THRESHOLD,
        "quarantined": quarantined[:50],
        "quarantined_count": len(quarantined),
    }


def ev_distinct(sources: list[str]) -> int:
    return len(set(s.strip().lower() for s in sources if s))
