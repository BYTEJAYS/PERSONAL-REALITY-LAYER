"""Pattern-Based Memory (Memory-Architecture V3).

Life is mostly repetition. The vision says: don't store "wake / breakfast / work
/ sleep" 365×30 times — store the *Daily Pattern* once, then only the
*exceptions* (the Goa trip, the wedding, the job change). This module learns a
person's typical day from a stream of daily records and surfaces the deviations.

The pure core (`learn_pattern` + `find_exceptions`) works on plain day records
and is unit-testable; `build(db)` derives the records from the Memory store.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


@dataclass
class DayRecord:
    date: str                          # YYYY-MM-DD
    tags: frozenset[str] = frozenset()  # what happened that day (sources/entities/types)
    volume: int = 0                    # number of memories that day


@dataclass
class DailyPattern:
    core_tags: list[str] = field(default_factory=list)        # in the majority of days
    occasional_tags: list[str] = field(default_factory=list)  # recurring but not daily
    typical_volume: float = 0.0                               # median day size
    volume_mad: float = 0.0
    days_observed: int = 0


@dataclass
class Exception:
    date: str
    kind: str                          # novel | surge | absent_routine | quiet
    detail: str
    novelty: float = 0.0               # 0..1-ish strength

    def as_dict(self) -> dict:
        return {"date": self.date, "kind": self.kind, "detail": self.detail,
                "novelty": round(self.novelty, 3)}


def learn_pattern(days: list[DayRecord], core_frac: float = 0.5,
                  occasional_frac: float = 0.15) -> DailyPattern:
    if not days:
        return DailyPattern()
    n = len(days)
    freq: Counter[str] = Counter()
    for d in days:
        freq.update(set(d.tags))
    core = sorted([t for t, c in freq.items() if c / n >= core_frac])
    occ = sorted([t for t, c in freq.items()
                  if occasional_frac <= c / n < core_frac])
    vols = [d.volume for d in days]
    med = _median(vols)
    mad = _median([abs(v - med) for v in vols])
    return DailyPattern(core, occ, med, mad, n)


def find_exceptions(days: list[DayRecord], pattern: DailyPattern,
                    surge_k: float = 2.5) -> list[Exception]:
    """A day is an exception when it does something the pattern doesn't explain:
    novel activities, an activity surge, an absent routine, or an unusually quiet
    active day. Priority is novel → surge → absent_routine → quiet (most to least
    informative)."""
    known = set(pattern.core_tags) | set(pattern.occasional_tags)
    core = set(pattern.core_tags)
    med, mad = pattern.typical_volume, pattern.volume_mad
    surge_cut = med + surge_k * max(mad, 1.0)
    out: list[Exception] = []

    for d in days:
        novel = sorted(set(d.tags) - known)
        if novel:
            out.append(Exception(d.date, "novel",
                                 "new: " + ", ".join(novel[:4]),
                                 min(1.0, len(novel) / 3.0)))
            continue
        if d.volume > surge_cut and med > 0:
            out.append(Exception(d.date, "surge",
                                 f"{d.volume} vs typical {med:g}",
                                 min(1.0, (d.volume - med) / (med + 1))))
            continue
        if core and d.volume > 0:
            missing = core - set(d.tags)
            if len(missing) / len(core) >= 0.6:
                out.append(Exception(d.date, "absent_routine",
                                     "missing: " + ", ".join(sorted(missing)[:4]),
                                     len(missing) / len(core)))
                continue
        if med >= 3 and 0 < d.volume < med * 0.4:
            out.append(Exception(d.date, "quiet",
                                 f"{d.volume} vs typical {med:g}", 0.4))
    return out


def summarize(days: list[DayRecord]) -> dict:
    pattern = learn_pattern(days)
    exceptions = find_exceptions(days, pattern)
    total = len(days)
    return {
        "ready": total > 0,
        "days_observed": total,
        "pattern": pattern.__dict__,
        "exceptions": [e.as_dict() for e in exceptions],
        # store 1 pattern + the exceptions instead of every day
        "stored_units": 1 + len(exceptions) if total else 0,
        "compression_ratio": round((1 + len(exceptions)) / total, 3) if total else 0.0,
    }


# --- DB adapter -------------------------------------------------------------
def build(db) -> dict:
    from sqlalchemy import func, select
    from .models import Entity, Memory, MemoryEntity

    # One record per active day: tags = sources + memory types + linked entities.
    rows = db.execute(
        select(func.to_char(Memory.ts, "YYYY-MM-DD"), Memory.source, Memory.memory_type)
    ).all()
    ent_rows = db.execute(
        select(func.to_char(Memory.ts, "YYYY-MM-DD"), Entity.name)
        .join(MemoryEntity, MemoryEntity.memory_id == Memory.id)
        .join(Entity, Entity.id == MemoryEntity.entity_id)
    ).all()

    tags_by_day: dict[str, set[str]] = {}
    vol_by_day: Counter[str] = Counter()
    for day, source, mtype in rows:
        tags_by_day.setdefault(day, set()).update(
            t for t in (f"src:{source}", f"type:{mtype}") if t
        )
        vol_by_day[day] += 1
    for day, name in ent_rows:
        tags_by_day.setdefault(day, set()).add(f"ent:{name}")

    days = [
        DayRecord(date=day, tags=frozenset(tags), volume=vol_by_day[day])
        for day, tags in sorted(tags_by_day.items())
    ]
    result = summarize(days)
    result["generated_at"] = _now().isoformat()
    return result
