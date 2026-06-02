"""Personal Operating System (V2).

The navigation layer. It composes the cognitive engines into a single map:

    Current State → Desired State → Distance → Obstacles → Leverage Points

Current state comes from the digital twin + habits; desired state from stated
goals; distance from the claim-vs-pursuit gap; obstacles from blind-spot risks;
leverage points from blind-spot opportunities + the highest-impact counterfactuals.

`compose()` is pure (engine-output dicts in, navigation map out) and unit-testable;
`build(db)` runs the real engines and composes them.
"""

from __future__ import annotations

from datetime import datetime, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _round(x: float) -> float:
    return round(x, 3)


# --- pure composition -------------------------------------------------------
def _current(model: dict, habits: dict) -> dict:
    traits = [
        {"label": t.get("label"), "score": t.get("score")}
        for t in (model.get("traits") or [])
    ]
    focus = [k.get("skill") for k in (model.get("knowledge_distribution") or [])][:5]
    stable = [
        h.get("name") for h in (habits.get("habits") or [])
        if h.get("stage") in ("stable", "growing")
    ][:5]
    return {
        "summary": model.get("summary", "Model still forming."),
        "maturity": model.get("maturity"),
        "traits": traits,
        "active_focus": [f for f in focus if f],
        "established_habits": stable,
    }


def _desired(identity: dict) -> dict:
    goals = sorted(
        (
            {"goal": a.get("goal"), "priority": a.get("claim_strength", 0)}
            for a in (identity.get("alignments") or [])
        ),
        key=lambda g: g["priority"],
        reverse=True,
    )
    return {"goals": goals}


def _distance(identity: dict) -> dict:
    gaps = []
    for a in identity.get("alignments") or []:
        claim = a.get("claim_strength", 0)
        pursuit = a.get("pursuit_share", 0)
        gaps.append({
            "goal": a.get("goal"),
            "current_pursuit": pursuit,
            "desired_priority": claim,
            "distance": _round(max(0.0, claim - pursuit)),
            "note": a.get("explanation", ""),
        })
    gaps.sort(key=lambda g: g["distance"], reverse=True)
    weight = sum(g["desired_priority"] for g in gaps)
    overall = _round(sum(g["distance"] * g["desired_priority"] for g in gaps) / weight) if weight else 0.0
    return {"overall": overall, "per_goal": gaps}


def _obstacles(blind: dict) -> list[dict]:
    obs = [
        {"title": b.get("title"), "detail": b.get("finding"),
         "severity": b.get("severity", 0), "source": b.get("references", [])}
        for b in (blind.get("blind_spots") or [])
        if b.get("category") in ("risk", "misalignment", "pattern")
    ]
    obs.sort(key=lambda o: o["severity"], reverse=True)
    return obs[:6]


def _leverage(blind: dict, sim: dict, distance: dict) -> list[dict]:
    pts: list[dict] = []

    # Opportunities the engines already surfaced.
    for b in blind.get("blind_spots") or []:
        if b.get("category") == "opportunity":
            pts.append({
                "action": f"Lean into: {b.get('title')}",
                "rationale": b.get("finding"),
                "expected_effect": "Reinforces a condition already linked to your best output.",
                "impact": _round(b.get("severity", 0)),
                "source": "blind_spots",
            })

    # Counterfactuals with the biggest upside.
    cfs = sorted(
        (c for c in (sim.get("counterfactuals") or [])),
        key=lambda c: abs(c.get("delta_pct", 0)),
        reverse=True,
    )
    for c in cfs[:2]:
        pts.append({
            "action": c.get("premise"),
            "rationale": c.get("explanation"),
            "expected_effect": f"~{c.get('delta_pct')}% change over {c.get('horizon')}.",
            "impact": _round(min(1.0, abs(c.get("delta_pct", 0)) / 200)),
            "source": "life_sim",
        })

    # The single widest goal gap is itself a leverage point.
    top_gap = (distance.get("per_goal") or [None])[0]
    if top_gap and top_gap["distance"] >= 0.1:
        pts.append({
            "action": f"Shift more activity toward '{top_gap['goal']}'",
            "rationale": top_gap["note"],
            "expected_effect": "Closes the largest gap between what you value and what you do.",
            "impact": _round(top_gap["distance"]),
            "source": "identity",
        })

    pts.sort(key=lambda p: p["impact"], reverse=True)
    return pts[:6]


def compose(model: dict, identity: dict, blind: dict, sim: dict, habits: dict) -> dict:
    current = _current(model, habits)
    desired = _desired(identity)
    distance = _distance(identity)
    obstacles = _obstacles(blind)
    leverage = _leverage(blind, sim, distance)

    ready = bool(current["traits"] or desired["goals"] or obstacles or leverage)
    return {
        "generated_at": _now().isoformat(),
        "ready": ready,
        "note": "A navigation map built from your own data — orientation, not instruction.",
        "current_state": current,
        "desired_state": desired,
        "distance": distance,
        "obstacles": obstacles,
        "leverage_points": leverage,
    }


# --- DB adapter -------------------------------------------------------------
def build(db) -> dict:
    from . import blind_spots, cognitive_model, habit_genome, identity as identity_mod, life_sim

    def safe(fn):
        try:
            return fn(db)
        except Exception:
            return {}

    result = compose(
        safe(cognitive_model.build),
        safe(identity_mod.assess),
        safe(blind_spots.build),
        safe(life_sim.simulate),
        safe(habit_genome.build),
    )
    if not result["ready"]:
        result["message"] = "Not enough signal yet to build your navigation map."
    return result
