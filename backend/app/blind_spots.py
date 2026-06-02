"""Blind-Spot Detection (V2).

Synthesises the other cognitive engines (Decision Genome, Habit Genome, Identity
model, Predictions) to surface *hidden structures* the user is unlikely to see on
their own — repeated failure causes, success patterns, claim/behaviour gaps,
quietly-dying investments, hidden drivers of productivity.

It reveals; it does not scold. Language stays neutral and every finding carries
its evidence, confidence, and which engine(s) support it.

The detectors are pure (they take engine-output dicts) so they unit-test with
synthetic inputs; `build(db)` runs the real engines and feeds them in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class BlindSpot:
    kind: str
    category: str            # risk | pattern | opportunity | misalignment
    title: str
    finding: str             # the hidden structure, plainly stated
    severity: float          # 0..1 how notable it is
    confidence: float
    references: list[str] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)


# --- detectors (pure) -------------------------------------------------------
def from_decisions(d: dict) -> list[BlindSpot]:
    if not d.get("ready"):
        return []
    out: list[BlindSpot] = []
    conf = d.get("confidence", 0.5)
    count = d.get("decision_count", 0)
    rate = d.get("followthrough_rate", 1.0)
    abandoned = d.get("outcome_counts", {}).get("abandoned", 0)

    if count >= 4 and rate < 0.5:
        out.append(BlindSpot(
            "serial_starter", "pattern", "You start more than you finish",
            f"{abandoned} of {count} initiatives were abandoned; only "
            f"{round(rate * 100)}% reached sustained follow-through.",
            round(1 - rate, 3), conf, ["decision_genome"],
            {"decisions": count, "followthrough_rate": rate, "abandoned": abandoned},
        ))

    for p in d.get("patterns", []):
        lift = p.get("lift", 0)
        if lift <= -0.2:
            out.append(BlindSpot(
                f"decision_antipattern_{p['name']}", "risk",
                "A repeated decision mistake", p.get("observation", ""),
                round(abs(lift), 3), p.get("confidence", conf), ["decision_genome"],
                {"pattern": p.get("name"), "lift": lift},
            ))
        elif lift >= 0.3:
            out.append(BlindSpot(
                f"decision_success_{p['name']}", "opportunity",
                "A repeatable success condition", p.get("observation", ""),
                round(lift, 3), p.get("confidence", conf), ["decision_genome"],
                {"pattern": p.get("name"), "lift": lift},
            ))
    return out


def from_habits(d: dict) -> list[BlindSpot]:
    if not d.get("ready"):
        return []
    out: list[BlindSpot] = []
    habits = d.get("habits", [])
    conf = d.get("confidence", 0.5)

    # Investments you built up that are quietly fading.
    fading = [
        h for h in habits
        if h.get("stage") in ("declining", "dormant", "dead") and h.get("consistency", 0) >= 0.4
    ]
    fading.sort(key=lambda h: h.get("consistency", 0), reverse=True)
    for h in fading[:2]:
        out.append(BlindSpot(
            f"fading_investment_{h['name']}", "risk",
            "A habit you built is quietly fading",
            f"'{h['name']}' was active in {round(h['consistency'] * 100)}% of recent weeks "
            f"but is now {h['stage']}.",
            round(h["consistency"] * (1.0 if h["stage"] == "dead" else 0.6), 3),
            conf, ["habit_genome"],
            {"stage": h["stage"], "consistency": h["consistency"]},
        ))

    # Hidden driver: the habit most correlated with your productive weeks.
    corr = [h for h in habits if h.get("outcome_correlation", 0) >= 0.5]
    if corr:
        best = max(corr, key=lambda h: h["outcome_correlation"])
        out.append(BlindSpot(
            f"hidden_driver_{best['name']}", "opportunity",
            "A hidden driver of your productive weeks",
            f"Your more productive weeks consistently coincide with '{best['name']}' "
            f"(r={best['outcome_correlation']}).",
            round(best["outcome_correlation"], 3), conf, ["habit_genome"],
            {"correlation": best["outcome_correlation"]},
        ))
    return out


def from_identity(d: dict) -> list[BlindSpot]:
    if not d.get("ready"):
        return []
    out: list[BlindSpot] = []
    conf = d.get("confidence", 0.5)
    for a in d.get("alignments", []):
        if a.get("contradiction"):
            out.append(BlindSpot(
                f"claim_gap_{a['goal']}", "misalignment",
                "A goal you claim but rarely pursue", a.get("explanation", ""),
                round(a.get("claim_strength", 0) - a.get("pursuit_share", 0), 3),
                conf, ["identity"],
                {"claim": a.get("claim_strength"), "pursuit": a.get("pursuit_share")},
            ))
    return out


def from_predictions(d: dict) -> list[BlindSpot]:
    out: list[BlindSpot] = []
    for p in d.get("predictions", []):
        if p.get("kind") == "burnout_risk" and p.get("probability", 0) >= 0.55:
            out.append(BlindSpot(
                "burnout_risk", "risk", "Rising strain you may not have noticed",
                p.get("explanation", ""), round(p["probability"], 3),
                p.get("confidence", 0.5), ["prediction_engine"], p.get("evidence", {}),
            ))
    return out


def synthesize(decisions: dict, habits: dict, identity: dict, predictions: dict) -> dict:
    spots: list[BlindSpot] = []
    spots += from_decisions(decisions)
    spots += from_habits(habits)
    spots += from_identity(identity)
    spots += from_predictions(predictions)

    # Most notable first: severity weighted by how much data backs it.
    spots.sort(key=lambda s: s.severity * s.confidence, reverse=True)
    by_cat: dict[str, int] = {}
    for s in spots:
        by_cat[s.category] = by_cat.get(s.category, 0) + 1

    return {
        "generated_at": _now().isoformat(),
        "ready": len(spots) > 0,
        "note": "Hidden patterns surfaced from your own data. Descriptive, not prescriptive.",
        "category_counts": by_cat,
        "blind_spots": [s.__dict__ for s in spots[:10]],
    }


# --- DB adapter -------------------------------------------------------------
def build(db) -> dict:
    from . import decision_genome, habit_genome, identity as identity_mod, prediction_engine

    def safe(fn):
        try:
            return fn(db)
        except Exception:
            return {}

    result = synthesize(
        safe(decision_genome.build),
        safe(habit_genome.build),
        safe(identity_mod.assess),
        safe(prediction_engine.forecast),
    )
    if not result["ready"]:
        result["message"] = "Not enough cross-engine signal to surface blind spots yet."
    return result
