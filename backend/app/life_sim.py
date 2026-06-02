"""Life Simulation Engine (V2).

Projects the user's *current behaviour* forward into several plausible futures
(30d / 90d / 1y / 5y) and answers counterfactuals ("what if you practised
daily?"). Outputs are explicitly probabilistic extrapolations, never promises —
each carries the evidence and assumptions behind it. Never judges; only measures.

The numerical core is pure (no DB) so it is unit-testable with synthetic series;
`simulate(db)` is the thin adapter that pulls the series from the Memory store.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

HORIZONS: list[tuple[str, int]] = [
    ("30 days", 30),
    ("90 days", 90),
    ("1 year", 365),
    ("5 years", 1825),
]

# Plausible behavioural scenarios as multipliers on the current activity rate.
SCENARIOS: dict[str, float] = {"decline": 0.45, "steady": 1.0, "growth": 1.6}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _conf(n: float, scale: float, base: float = 0.3, cap: float = 0.9) -> float:
    return round(min(cap, base + n / scale), 2)


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _base_rate(weekly: list[int]) -> float:
    """Activity per week from the most recent 4 weeks (weekly is recent-last)."""
    recent = weekly[-4:] if len(weekly) >= 4 else weekly
    return _mean([float(x) for x in recent])


def _trend(weekly: list[int]) -> float:
    """Signed change: mean of last 2 weeks minus the 2 before."""
    if len(weekly) < 4:
        return 0.0
    return _mean([float(x) for x in weekly[-2:]]) - _mean([float(x) for x in weekly[-4:-2]])


# --- trajectories -----------------------------------------------------------
@dataclass
class Trajectory:
    scenario: str
    horizon: str
    projected_activity: int  # cumulative memories produced over the horizon
    active_share: float      # fraction of weeks expected to be active
    skills_kept: int
    skills_faded: int
    note: str


_ACTIVE_SHARE = {"decline": 0.3, "steady": 0.6, "growth": 0.85}
_FADE_DAYS = 180  # a skill unreinforced this long is treated as faded


def project_trajectories(
    weekly: list[int],
    skill_idle_days: list[int],
    horizons: list[tuple[str, int]] = HORIZONS,
) -> list[Trajectory]:
    rate = _base_rate(weekly)
    tr = _trend(weekly)
    out: list[Trajectory] = []
    for scen, factor in SCENARIOS.items():
        # The "steady" path inherits the observed trend; others assume a shift.
        eff_rate = max(0.0, rate * factor + (tr if scen == "steady" else 0.0))
        share = _ACTIVE_SHARE[scen]
        for hlabel, days in horizons:
            weeks = days / 7
            proj = int(round(eff_rate * weeks * share))
            # A skill fades if its idle time, plus the un-engaged portion of the
            # horizon, exceeds the fade threshold.
            kept = sum(1 for d in skill_idle_days if d + days * (1 - share) <= _FADE_DAYS)
            faded = len(skill_idle_days) - kept
            out.append(
                Trajectory(
                    scenario=scen,
                    horizon=hlabel,
                    projected_activity=proj,
                    active_share=share,
                    skills_kept=kept,
                    skills_faded=faded,
                    note=(
                        f"At a {scen} pace (~{round(eff_rate, 1)} signals/week) you'd log "
                        f"~{proj} memories over {hlabel}; {kept} of {len(skill_idle_days)} "
                        f"tracked skills stay reinforced."
                    ),
                )
            )
    return out


# --- counterfactuals --------------------------------------------------------
@dataclass
class Counterfactual:
    premise: str
    horizon: str
    baseline: float
    alternative: float
    delta_pct: float
    explanation: str
    evidence: dict = field(default_factory=dict)


def _delta_pct(base: float, alt: float) -> float:
    return round((alt - base) / base * 100, 1) if base else 0.0


def cf_daily_practice(active_days_per_week: list[int], horizon_days: int = 365) -> Counterfactual:
    mean_active = _mean([float(x) for x in active_days_per_week])
    weeks = horizon_days / 7
    base = round(mean_active * weeks)
    alt = round(7 * weeks)
    return Counterfactual(
        "If you were active every day",
        f"{horizon_days} days",
        base, alt, _delta_pct(base, alt),
        f"You're active ~{round(mean_active, 1)} day(s)/week. Daily practice would mean "
        f"~{int(alt - base)} more active days over {horizon_days} days.",
        {"current_active_days_per_week": round(mean_active, 1)},
    )


def cf_consistent_habit(active_days_per_week: list[int], horizon_days: int = 365) -> Counterfactual:
    if not active_days_per_week:
        return Counterfactual("If your habit were consistent", f"{horizon_days} days", 0, 0, 0,
                              "Not enough activity history yet.", {})
    mean_active = _mean([float(x) for x in active_days_per_week])
    best = max(active_days_per_week)
    weeks = horizon_days / 7
    base = round(mean_active * weeks)
    alt = round(best * weeks)
    return Counterfactual(
        "If every week matched your best week",
        f"{horizon_days} days",
        base, alt, _delta_pct(base, alt),
        f"Your best week hit {best} active days vs a ~{round(mean_active, 1)} average. "
        f"Closing that gap adds ~{int(alt - base)} active days a year.",
        {"best_week": best, "mean_week": round(mean_active, 1)},
    )


def cf_finish_projects(neglected: int, completion_rate: float, horizon_days: int = 365) -> Counterfactual:
    base = round(completion_rate, 1)
    alt = round(completion_rate + neglected, 1)
    return Counterfactual(
        "If you revived your stalled projects",
        f"{horizon_days} days",
        base, alt, _delta_pct(max(base, 1), alt),
        f"{neglected} project(s) have gone quiet. Reviving them could roughly "
        f"{'double' if neglected >= base else 'increase'} your completed output.",
        {"neglected_projects": neglected},
    )


# --- DB adapter -------------------------------------------------------------
def simulate(db) -> dict:
    """Pull behavioural series from the Memory store and run the simulation."""
    from datetime import timedelta
    from sqlalchemy import distinct, func, select
    from .models import Entity, Memory, MemoryEntity

    now = _now()

    weekly: list[int] = []
    active_dpw: list[int] = []
    for w in range(7, -1, -1):  # 8 weeks, recent last
        lo = now - timedelta(days=7 * (w + 1))
        hi = now - timedelta(days=7 * w)
        weekly.append(
            db.execute(select(func.count(Memory.id)).where(Memory.ts >= lo, Memory.ts < hi)).scalar_one()
        )
        active_dpw.append(
            db.execute(
                select(func.count(distinct(func.date(Memory.ts)))).where(Memory.ts >= lo, Memory.ts < hi)
            ).scalar_one()
        )

    total = sum(weekly)
    if total < 6:
        return {
            "generated_at": now.isoformat(),
            "ready": False,
            "message": "Not enough recent activity to simulate trajectories yet.",
        }

    skill_idle = [
        (now - mx).days
        for (mx,) in db.execute(
            select(func.max(Memory.ts))
            .join(MemoryEntity, MemoryEntity.memory_id == Memory.id)
            .join(Entity, Entity.id == MemoryEntity.entity_id)
            .where(Entity.type == "skill")
            .group_by(Entity.id)
        ).all()
        if mx
    ]

    proj_rows = db.execute(
        select(Entity.id, func.count(distinct(MemoryEntity.memory_id)), func.max(Memory.ts))
        .join(MemoryEntity, MemoryEntity.entity_id == Entity.id)
        .join(Memory, Memory.id == MemoryEntity.memory_id)
        .where(Entity.type == "project").group_by(Entity.id)
    ).all()
    neglected = sum(1 for _, n, mx in proj_rows if n >= 2 and mx and (now - mx).days > 21)
    active_projects = sum(1 for _, n, mx in proj_rows if mx and (now - mx).days <= 21)

    trajectories = project_trajectories(weekly, skill_idle)
    counterfactuals = [
        cf_daily_practice(active_dpw),
        cf_consistent_habit(active_dpw),
        cf_finish_projects(neglected, float(active_projects)),
    ]

    return {
        "generated_at": now.isoformat(),
        "ready": True,
        "disclaimer": "Plausible extrapolations from current behaviour — not predictions of fact.",
        "confidence": _conf(total, 60),
        "inputs": {
            "weekly_activity_8w": weekly,
            "active_days_per_week_8w": active_dpw,
            "tracked_skills": len(skill_idle),
            "neglected_projects": neglected,
        },
        "trajectories": [t.__dict__ for t in trajectories],
        "counterfactuals": [c.__dict__ for c in counterfactuals],
    }
