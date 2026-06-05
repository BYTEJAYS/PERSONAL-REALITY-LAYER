"""Memory Aging / Intelligent Forgetting (Memory-Architecture V3).

PRL should behave like biological memory: fresh memories stay high-resolution,
old ones compress to summaries, then stories, then only the major beats survive.
Importance resists aging — a wedding stays vivid for decades, an idle Tuesday
fades in a year.

The pure core maps (age, importance) → a detail *tier* and the fraction of raw
detail worth keeping, plus a Layer-0 raw-expiry rule (raw files live 1–6 months,
not forever). `build(db)` reports the aging distribution over the real store.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

# Detail tiers, coarsest last. Each keeps progressively less raw detail.
TIERS = ("full", "summary", "story", "gist", "faded")
TIER_DETAIL = {"full": 1.0, "summary": 0.5, "story": 0.2, "gist": 0.05, "faded": 0.01}

# Effective-age cut-offs (days) between tiers.
_CUTS = ((30, "full"), (365, "summary"), (5 * 365, "story"), (20 * 365, "gist"))

# Raw sensory layer (Layer 0) retention window in days, by importance.
RAW_MIN_DAYS = 30      # trivial raw memories expire after ~1 month
RAW_MAX_DAYS = 180     # important raw memories held the full ~6 months


def _now() -> datetime:
    return datetime.now(timezone.utc)


def effective_age(age_days: float, importance: float) -> float:
    """Important memories age slower. importance 0 → 1/0.4 faster, 1 → 1/1.6 slower."""
    importance = max(0.0, min(1.0, importance))
    return age_days / (0.4 + 1.2 * importance)


def age_tier(age_days: float, importance: float = 0.5) -> str:
    eff = effective_age(age_days, importance)
    for cut, tier in _CUTS:
        if eff < cut:
            return tier
    return "faded"


def target_detail(age_days: float, importance: float = 0.5) -> float:
    """Fraction of raw detail worth retaining for a memory of this age/importance."""
    return TIER_DETAIL[age_tier(age_days, importance)]


def raw_expired(age_days: float, importance: float = 0.5) -> bool:
    """Layer 0: has this raw sensory file outlived its retention window?"""
    importance = max(0.0, min(1.0, importance))
    window = RAW_MIN_DAYS + (RAW_MAX_DAYS - RAW_MIN_DAYS) * importance
    return age_days > window


@dataclass
class AgingItem:
    id: str
    age_days: float
    importance: float = 0.5
    source: str = ""


def retention_plan(items: list[AgingItem]) -> dict:
    """Summarise how a memory set ages: tier distribution, the meaning-compression
    ratio (kept detail / full detail), and which raw files are due to expire."""
    if not items:
        return {"count": 0, "tiers": {t: 0 for t in TIERS}, "compression_ratio": 1.0,
                "raw_expired": 0}

    tiers = {t: 0 for t in TIERS}
    kept = 0.0
    expired = 0
    for it in items:
        t = age_tier(it.age_days, it.importance)
        tiers[t] += 1
        kept += TIER_DETAIL[t]
        if raw_expired(it.age_days, it.importance):
            expired += 1

    return {
        "count": len(items),
        "tiers": tiers,
        # 1.0 = nothing compressed; lower = more meaning-compression achieved.
        "compression_ratio": round(kept / len(items), 3),
        "raw_expired": expired,
    }


# --- DB adapter -------------------------------------------------------------
def build(db) -> dict:
    from sqlalchemy import select
    from .models import Memory

    now = _now()
    rows = db.execute(select(Memory.id, Memory.ts, Memory.importance, Memory.source)).all()
    items = []
    for mid, ts, imp, source in rows:
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = (now - ts).total_seconds() / 86400.0
        items.append(AgingItem(str(mid), age, imp if imp is not None else 0.5, source or ""))

    plan = retention_plan(items)
    # Memories the aging policy says should compress now (older than full-detail).
    to_compress = [it for it in items if age_tier(it.age_days, it.importance) != "full"]
    return {
        "generated_at": now.isoformat(),
        "ready": plan["count"] > 0,
        **plan,
        "due_for_compression": len(to_compress),
        "policy": {
            "tiers": list(TIERS),
            "tier_detail": TIER_DETAIL,
            "raw_window_days": [RAW_MIN_DAYS, RAW_MAX_DAYS],
        },
    }
