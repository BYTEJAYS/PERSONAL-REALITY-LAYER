"""Truth Extraction Engine — the apex of the Meta-Wisdom Cortex.

Memory stores experiences. Knowledge stores understanding. Wisdom stores lessons.
**Meta-Wisdom stores truths.**

A *truth* is a principle that has earned the highest standing: it has been held
long enough, backed by enough evidence, corroborated by enough *independent*
sources, and never overturned by contradiction. Most principles never become
truths — and that's the point. Truths emerge slowly, over years.

For each principle we compute a ``truthhood`` score in [0,1] from five signals:

    confidence  — how sure the underlying data makes us
    evidence    — how many data points back it (log-scaled)
    longevity   — how long it has been continuously held
    sources     — how many independent engines corroborate it
    stability   — 1.0 unless it's contradicted / weakening / dormant

Principles at or above the threshold (and uncontradicted, still active) are
**truths**; the rest are **emerging truths**, shown with their progress so you can
watch them climb. Pure functions (DB-free, unit-tested); ``build(db)`` reads the
stored principles + the contradiction view and classifies them. Read-only.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

# Weights sum to 1.0.
W_CONFIDENCE = 0.30
W_EVIDENCE = 0.25
W_LONGEVITY = 0.20
W_SOURCES = 0.15
W_STABILITY = 0.10

TRUTH_THRESHOLD = 0.70
_LONGEVITY_HORIZON_DAYS = 365     # ~a year of being held reads as full longevity
_EVIDENCE_SATURATION = 30         # ~30 data points reads as full evidence
_SOURCE_SATURATION = 3            # 3+ independent sources reads as full corroboration


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _age_days(iso: str, now_iso: str) -> float:
    try:
        return (datetime.fromisoformat(now_iso) - datetime.fromisoformat(iso)).total_seconds() / 86400.0
    except (ValueError, TypeError):
        return 0.0


def _evidence_score(ec: int) -> float:
    return min(1.0, math.log2(1 + max(0, ec)) / math.log2(1 + _EVIDENCE_SATURATION))


def _longevity_score(first_seen: str, now_iso: str) -> float:
    return min(1.0, max(0.0, _age_days(first_seen, now_iso)) / _LONGEVITY_HORIZON_DAYS)


def _source_score(sources: list) -> float:
    return min(1.0, len(set(sources or [])) / _SOURCE_SATURATION)


def truthhood(principle: dict, now_iso: str, contradicted_keys: set[str]) -> tuple[float, dict]:
    """Score a principle's claim to being a timeless truth, with its components."""
    conf = float(principle.get("confidence", 0.0))
    ev = _evidence_score(int(principle.get("evidence_count", 1)))
    lon = _longevity_score(principle.get("first_seen", now_iso), now_iso)
    src = _source_score(principle.get("sources", []))
    contested = (principle.get("key") in contradicted_keys
                 or principle.get("status") in ("weakening", "dormant"))
    stab = 0.0 if contested else 1.0
    score = (W_CONFIDENCE * conf + W_EVIDENCE * ev + W_LONGEVITY * lon
             + W_SOURCES * src + W_STABILITY * stab)
    components = {
        "confidence": round(conf, 3), "evidence": round(ev, 3),
        "longevity": round(lon, 3), "sources": round(src, 3), "stability": stab,
    }
    return round(score, 3), components


def contradicted_keys(contradictions: list[dict]) -> set[str]:
    """Keys of principles currently in tension (opposing or abandoned). A revision
    is an *update*, not a live contradiction, so it doesn't count against truth."""
    out: set[str] = set()
    for c in contradictions or []:
        if c.get("type") == "opposing":
            out.update(k for k in c.get("keys", []) if k)
        elif c.get("type") == "abandoned" and c.get("key"):
            out.add(c["key"])
    return out


def classify(principles: list[dict], contradictions: list[dict], now_iso: str,
             threshold: float = TRUTH_THRESHOLD) -> tuple[list[dict], list[dict]]:
    """Split principles into (truths, emerging) by truthhood. Returns both sorted
    by score descending; emerging items carry the gap remaining to truth-hood."""
    contested = contradicted_keys(contradictions)
    truths: list[dict] = []
    emerging: list[dict] = []
    for p in principles:
        score, comp = truthhood(p, now_iso, contested)
        is_contested = p.get("key") in contested
        item = {
            "key": p.get("key"),
            "statement": p.get("statement"),
            "category": p.get("category"),
            "truthhood": score,
            "components": comp,
            "confidence": p.get("confidence"),
            "evidence_count": p.get("evidence_count"),
            "first_seen": p.get("first_seen"),
            "sources": sorted(set(p.get("sources", []))),
            "contradicted": is_contested,
        }
        if score >= threshold and p.get("status") == "active" and not is_contested:
            truths.append(item)
        else:
            item["to_truth"] = round(max(0.0, threshold - score), 3)
            emerging.append(item)
    truths.sort(key=lambda x: x["truthhood"], reverse=True)
    emerging.sort(key=lambda x: x["truthhood"], reverse=True)
    return truths, emerging


# --- DB adapter (read-only) -------------------------------------------------
def build(db, threshold: float = TRUTH_THRESHOLD, emerging_limit: int = 12) -> dict:
    """Read standing principles + contradictions and classify into truths/emerging."""
    from . import philosophy_engine

    principles = philosophy_engine._load_principles(db)
    contradictions = philosophy_engine.detect_contradictions(principles)
    now = _now_iso()
    truths, emerging = classify(principles, contradictions, now, threshold)

    return {
        "generated_at": now,
        "ready": bool(principles),
        "note": "Truths are principles that have survived long enough, with enough "
                "evidence from enough independent sources, never overturned. They "
                "emerge slowly — most principles stay 'emerging' for years.",
        "threshold": threshold,
        "weights": {"confidence": W_CONFIDENCE, "evidence": W_EVIDENCE,
                    "longevity": W_LONGEVITY, "sources": W_SOURCES, "stability": W_STABILITY},
        "truth_count": len(truths),
        "truths": truths,
        "emerging": emerging[:emerging_limit],
    }
