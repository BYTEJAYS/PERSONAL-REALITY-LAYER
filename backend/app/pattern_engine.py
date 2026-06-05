"""Layer 4 — Pattern Discovery Engine.

The closest thing to an ML core: rather than hardcoded observations, it builds a
daily behavioural feature frame and *searches* for statistical relationships —
both contemporaneous ("on days you build more, you also learn more") and
time-lagged ("a stretch with no social contact tends to be followed by a dip").
Pure-Python statistics (no heavy deps). Every pattern carries correlation
strength, confidence, sample size, and evidence — and nothing is emitted below
the data threshold, so it never invents a correlation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Entity, Memory, MemoryEntity
from .rhythm import best_window

# Human labels + which pattern category a feature belongs to.
FEATURES: dict[str, tuple[str, str]] = {
    "activity": ("overall activity", "behavioral"),
    "productivity": ("focused/important work", "productivity"),
    "learning": ("learning", "learning"),
    "building": ("hands-on building", "learning"),
    "reading": ("reading/study", "learning"),
    "social": ("social interaction", "social"),
    "late_share": ("late-night work", "productivity"),
    "new_skills": ("picking up new skills", "learning"),
}

MIN_DAYS = 10          # need at least this many active days to trust a correlation
MIN_R = 0.35           # minimum |Pearson r|


@dataclass
class Pattern:
    kind: str           # correlation | lag | peak_window | comparison
    category: str
    statement: str
    strength: float     # r, or share for window patterns
    confidence: float
    sample_size: int
    explanation: str
    evidence: dict = field(default_factory=dict)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _pearson(xs: list[float], ys: list[float]) -> tuple[float, int]:
    n = len(xs)
    if n < 3:
        return 0.0, n
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    sxx = sum((a - mx) ** 2 for a in xs)
    syy = sum((b - my) ** 2 for b in ys)
    if sxx == 0 or syy == 0:
        return 0.0, n
    return sxy / math.sqrt(sxx * syy), n


def _confidence(r: float, n: int) -> float:
    if n < 4:
        return 0.3
    t = abs(r) * math.sqrt((n - 2) / max(1e-9, 1 - r * r))  # t-statistic
    return round(min(0.9, 0.3 + 0.6 * min(t / 6.0, 1.0)), 2)


# --- feature frame ----------------------------------------------------------
def _daily_features(db: Session) -> dict[date, dict[str, float]]:
    mems = db.execute(
        select(Memory.id, Memory.ts, Memory.memory_type, Memory.importance)
    ).all()
    if not mems:
        return {}

    links = db.execute(
        select(MemoryEntity.memory_id, Entity.type, Entity.name)
        .join(Entity, Entity.id == MemoryEntity.entity_id)
    ).all()

    per_mem: dict = {}
    skill_first: dict[str, date] = {}
    ts_by_mem = {mid: ts for mid, ts, _, _ in mems}
    for mid, etype, ename in links:
        rec = per_mem.setdefault(mid, {"skill": False, "project": False, "persons": 0})
        if etype == "skill":
            rec["skill"] = True
            d = ts_by_mem[mid].date()
            if ename not in skill_first or d < skill_first[ename]:
                skill_first[ename] = d
        elif etype == "project":
            rec["project"] = True
        elif etype == "person":
            rec["persons"] += 1

    frame: dict[date, dict[str, float]] = {}
    late: dict[date, int] = {}
    for mid, ts, mtype, imp in mems:
        d = ts.date()
        f = frame.setdefault(d, {k: 0.0 for k in FEATURES})
        rec = per_mem.get(mid, {"skill": False, "project": False, "persons": 0})
        f["activity"] += 1
        f["productivity"] += float(imp)
        if rec["skill"]:
            f["learning"] += 1
            f["building" if rec["project"] else "reading"] += 1
        if mtype == "social":
            f["social"] += 1
        late[d] = late.get(d, 0) + (1 if ts.hour >= 21 else 0)

    for sk, d in skill_first.items():
        if d in frame:
            frame[d]["new_skills"] += 1
    for d, f in frame.items():
        f["late_share"] = late.get(d, 0) / f["activity"] if f["activity"] else 0.0
    return frame


# --- searchers --------------------------------------------------------------
def _correlations(frame: dict[date, dict[str, float]]) -> list[Pattern]:
    days = sorted(frame)
    if len(days) < MIN_DAYS:
        return []
    out: list[Pattern] = []
    for a, b in combinations(FEATURES, 2):
        xs = [frame[d][a] for d in days]
        ys = [frame[d][b] for d in days]
        # Skip features that never vary (e.g. no reading days).
        if len(set(xs)) < 3 or len(set(ys)) < 3:
            continue
        r, n = _pearson(xs, ys)
        if abs(r) < MIN_R:
            continue
        la, ca = FEATURES[a]
        lb, cb = FEATURES[b]
        direction = "more" if r > 0 else "less"
        out.append(Pattern(
            "correlation", ca if ca != "behavioral" else cb,
            f"On days with more {la}, you tend to do {direction} {lb}.",
            round(r, 2), _confidence(r, n), n,
            f"Pearson r={round(r,2)} across {n} active days.",
            {"feature_a": a, "feature_b": b, "r": round(r, 3)},
        ))
    return out


def _lagged(frame: dict[date, dict[str, float]]) -> list[Pattern]:
    days = sorted(frame)
    # Build consecutive-day pairs (d, d+1).
    pairs = [(days[i], days[i + 1]) for i in range(len(days) - 1)
             if (days[i + 1] - days[i]).days == 1]
    if len(pairs) < MIN_DAYS:
        return []
    causes = ["social", "building", "late_share", "activity"]
    effects = ["activity", "productivity", "learning"]
    out: list[Pattern] = []
    for a in causes:
        for b in effects:
            if a == b:
                continue
            xs = [frame[d0][a] for d0, _ in pairs]
            ys = [frame[d1][b] for _, d1 in pairs]
            if len(set(xs)) < 3 or len(set(ys)) < 3:
                continue
            r, n = _pearson(xs, ys)
            if abs(r) < MIN_R + 0.05:  # slightly stricter for causal-looking claims
                continue
            la, ca = FEATURES[a]
            lb, _ = FEATURES[b]
            if r > 0:
                stmt = f"More {la} tends to be followed the next day by more {lb}."
            else:
                stmt = f"After a day heavy on {la}, your {lb} tends to dip the next day."
            out.append(Pattern(
                "lag", ca if ca != "behavioral" else "behavioral", stmt,
                round(r, 2), _confidence(r, n), n,
                f"Lag-1 correlation r={round(r,2)} over {n} consecutive-day pairs.",
                {"cause": a, "effect": b, "r": round(r, 3), "lag_days": 1},
            ))
    return out


def _peak_window(db: Session) -> Pattern | None:
    rows = db.execute(select(Memory.ts, Memory.importance)).all()
    if len(rows) < 15:
        return None
    weight = [0.0] * 24
    for ts, imp in rows:
        weight[ts.hour] += float(imp)
    if sum(weight) == 0:
        return None
    # Same shared best-window logic the Cognitive Twin's rhythm trait uses.
    h1, h2, best_share = best_window(weight, 4)
    if best_share < 0.30:
        return None
    return Pattern(
        "peak_window", "productivity",
        f"Your productivity peaks between {h1:02d}:00 and {h2:02d}:00.",
        round(best_share, 2), round(min(0.9, 0.4 + best_share), 2), len(rows),
        f"{round(best_share*100)}% of your weighted activity falls in that 4-hour window (UTC).",
        {"window": [h1, h2], "share": round(best_share, 3)},
    )


def discover(db: Session) -> dict:
    frame = _daily_features(db)
    patterns = _correlations(frame) + _lagged(frame)
    pw = _peak_window(db)
    if pw:
        patterns.append(pw)
    # Strongest, most-confident first.
    patterns.sort(key=lambda p: abs(p.strength) * p.confidence, reverse=True)
    return {
        "generated_at": _now().isoformat(),
        "active_days_analyzed": len(frame),
        "count": len(patterns),
        "note": "Correlation is not causation; these are statistical tendencies in your data.",
        "patterns": [p.__dict__ for p in patterns[:12]],
    }
