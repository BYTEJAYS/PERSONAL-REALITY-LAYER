"""Event Simulator (Reality OS) — #15, PARTIAL → BUILT.

Hypothetical reasoning: "what if I move cities / leave my job / start a company /
invest here?". Given the user's current life-state across domains, the simulator
applies a scenario's modelled effects, projects the resulting state, and reports
the net change, the trade-offs (what improves vs. what suffers) and a confidence.
It turns PRL into a decision-support system rather than a record.

Pure ``simulate`` / ``compare`` are DB-free and unit-testable; ``build(db)``
sources the current state from the Personal World Model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

# Modelled scenarios: per-domain effect in [-1,1] applied to current state, plus a
# confidence reflecting how predictable the scenario is.
SCENARIOS: dict[str, dict] = {
    "move_city": {
        "label": "Move to a new city",
        "effects": {"social": -0.3, "behaviour": -0.15, "emotional": -0.1,
                    "finance": -0.1, "knowledge": 0.1},
        "confidence": 0.5,
    },
    "leave_job": {
        "label": "Leave current job",
        "effects": {"finance": -0.4, "emotional": 0.1, "behaviour": -0.2,
                    "projects": 0.2, "knowledge": 0.1},
        "confidence": 0.45,
    },
    "start_company": {
        "label": "Start a company",
        "effects": {"finance": -0.3, "projects": 0.4, "behaviour": -0.25,
                    "emotional": -0.1, "social": -0.1, "knowledge": 0.2},
        "confidence": 0.4,
    },
    "invest": {
        "label": "Make a significant investment",
        "effects": {"finance": 0.2},
        "confidence": 0.5,
    },
    "daily_exercise": {
        "label": "Exercise daily",
        "effects": {"health": 0.3, "emotional": 0.2, "behaviour": 0.15},
        "confidence": 0.7,
    },
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


@dataclass
class Outcome:
    scenario: str
    label: str
    confidence: float
    before: dict = field(default_factory=dict)
    after: dict = field(default_factory=dict)
    net_change: float = 0.0
    gains: list[str] = field(default_factory=list)
    losses: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "scenario": self.scenario, "label": self.label,
            "confidence": round(self.confidence, 3),
            "net_change": round(self.net_change, 3),
            "gains": self.gains, "losses": self.losses,
            "before": {k: round(v, 3) for k, v in self.before.items()},
            "after": {k: round(v, 3) for k, v in self.after.items()},
        }


def simulate(state: dict, scenario: str, effects: dict | None = None,
             confidence: float | None = None, label: str | None = None) -> dict:
    """Apply a scenario to the current `state` (domain → 0..1) and project outcomes.
    Pass a preset name, or supply custom `effects`/`confidence`."""
    if effects is None:
        preset = SCENARIOS.get(scenario)
        if preset is None:
            return {"ready": False, "error": f"unknown scenario: {scenario}"}
        effects, confidence, label = preset["effects"], preset["confidence"], preset["label"]

    before = {k: _clamp(v) for k, v in state.items()}
    after = dict(before)
    gains, losses = [], []
    for dom, delta in effects.items():
        base = before.get(dom, 0.5)
        # Diminishing application: scaled by confidence, harder to move extremes.
        applied = delta * (confidence if confidence is not None else 0.5)
        nv = _clamp(base + applied)
        after[dom] = nv
        if nv - base > 0.02:
            gains.append(dom)
        elif nv - base < -0.02:
            losses.append(dom)

    net = (sum(after.values()) - sum(before.values()))
    out = Outcome(scenario, label or scenario, confidence if confidence is not None else 0.5,
                  before, after, net, gains, losses)
    return {"ready": True, **out.as_dict()}


def compare(state: dict, scenarios: list[str] | None = None) -> list[dict]:
    """Rank scenarios by projected net benefit (confidence-weighted)."""
    names = scenarios or list(SCENARIOS.keys())
    results = []
    for name in names:
        r = simulate(state, name)
        if r.get("ready"):
            r["score"] = round(r["net_change"] * r["confidence"], 3)
            results.append(r)
    results.sort(key=lambda r: -r["score"])
    return results


# --- DB adapter -------------------------------------------------------------
def _current_state(db) -> dict:
    from . import world_model
    world = world_model.build(db)
    return {d["domain"]: d["score"] for d in world.get("domains", [])
            if d.get("score") is not None}


def build(db, scenario: str | None = None) -> dict:
    state = _current_state(db)
    if not state:
        return {"ready": False, "message": "No life-state to simulate from yet."}
    if scenario:
        return {"generated_at": _now().isoformat(), "state": state, **simulate(state, scenario)}
    return {
        "ready": True,
        "generated_at": _now().isoformat(),
        "state": {k: round(v, 3) for k, v in state.items()},
        "scenarios": compare(state),
    }
