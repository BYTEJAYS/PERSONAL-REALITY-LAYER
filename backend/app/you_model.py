"""The You-Model — a from-scratch preference/decision engine.

This is the part of PRL that is uniquely *you*: not language (that's borrowed
from the local model), but judgement. It learns a utility function over the
*features* of a choice from your revealed behaviour — what you actually
sustained vs. abandoned — and uses it to score options the way you tend to.

Two sources combine into the final weights:

1. **Priors** derived from your cognitive twin's traits (curiosity, persistence,
   focus, collaboration, learning style). Available even with almost no data.
2. **Learned** weights from your revealed preferences: each past project is an
   example whose *value* is how well it followed through; we form pairwise
   comparisons (a good outcome should out-score a bad one) and fit weights with
   from-scratch pairwise-logistic gradient descent — no libraries, same spirit
   as the logreg predictor.

The blend is honest about data: with few comparisons we lean on priors and
report low confidence; as you feed in more (especially decisions you narrate),
the learned signal takes over. Pure stdlib so it unit-tests on any interpreter;
the DB adapter (`build`) is the only part that touches Postgres.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# The axes a choice is scored on. Each option is a dict of these in [0,1].
FEATURES = ("novelty", "continuation", "alignment", "solo", "depth", "momentum", "goal_fit")

# Readable phrasing for a positive / negative weight on each axis.
_AXIS_POS = {
    "novelty": "new, exploratory things",
    "continuation": "continuing what you've already started",
    "alignment": "work that fits your strongest skills",
    "solo": "working solo",
    "depth": "going deep on one thing",
    "momentum": "things you already have momentum on",
    "goal_fit": "work that serves a stated goal",
}
_AXIS_NEG = {
    "novelty": "sticking to the familiar",
    "continuation": "starting fresh over finishing",
    "alignment": "stretching outside your usual skills",
    "solo": "working with other people",
    "depth": "spreading across many things",
    "momentum": "cold-starting things",
    "goal_fit": "following curiosity over stated goals",
}


def _sigmoid(z: float) -> float:
    if z < -60:
        return 0.0
    if z > 60:
        return 1.0
    return 1.0 / (1.0 + math.exp(-z))


def _dot(w: dict[str, float], x: dict[str, float]) -> float:
    return sum(w.get(f, 0.0) * x.get(f, 0.0) for f in FEATURES)


def _conf(n: float, scale: float, base: float = 0.25, cap: float = 0.9) -> float:
    return round(min(cap, base + n / scale), 2)


# --- priors from the cognitive twin -----------------------------------------
def trait_priors(traits: list[dict]) -> dict[str, float]:
    """Map twin traits → a prior weight vector. Centred at 0 (no opinion)."""
    w = {f: 0.0 for f in FEATURES}
    for t in traits:
        name = (t.get("name") or "").lower()
        label = (t.get("label") or "").lower()
        score = float(t.get("score", 0.5))
        s = (score - 0.5) * 2  # -1..1, signed strength

        if "curiosity" in name:
            w["novelty"] += 0.8 * s
        elif "persistence" in name:
            w["continuation"] += 0.7 * s
            w["momentum"] += 0.5 * s
        elif "focus" in name:
            w["depth"] += 0.8 * s
        elif "collaborat" in name:
            # label tells direction: independent ⇒ prefers solo
            if "independent" in label or "solo" in label:
                w["solo"] += 0.7
            elif "collaborat" in label or "team" in label:
                w["solo"] -= 0.7
        elif "learning_style" in name or "learning style" in name:
            if "hands" in label or "builder" in label:
                w["alignment"] += 0.5
                w["depth"] += 0.3
    return w


# --- learning from revealed preference --------------------------------------
def learn_weights(
    examples: list[tuple[dict[str, float], float]],
    priors: dict[str, float],
    *,
    epochs: int = 400,
    lr: float = 0.3,
    l2: float = 0.05,
) -> tuple[dict[str, float], int, float]:
    """Fit weights from (features, value) examples via pairwise logistic GD.

    Returns (blended_weights, n_pairs, learn_strength). `learn_strength` (0..1)
    is how much the learned signal is trusted vs. priors, growing with #pairs.
    """
    # Build comparison pairs from examples that differ meaningfully in value.
    pairs: list[tuple[dict[str, float], dict[str, float]]] = []  # (winner, loser)
    for i in range(len(examples)):
        for j in range(len(examples)):
            if i == j:
                continue
            xi, vi = examples[i]
            xj, vj = examples[j]
            if vi - vj >= 0.15:  # i clearly preferred over j
                pairs.append((xi, xj))

    learned = {f: 0.0 for f in FEATURES}
    if pairs:
        for _ in range(epochs):
            grad = {f: 0.0 for f in FEATURES}
            for win, lose in pairs:
                diff = {f: win.get(f, 0.0) - lose.get(f, 0.0) for f in FEATURES}
                p = _sigmoid(_dot(learned, diff))
                err = 1.0 - p  # target: winner beats loser (prob 1)
                for f in FEATURES:
                    grad[f] += err * diff[f]
            for f in FEATURES:
                g = grad[f] / len(pairs) - l2 * learned[f]
                learned[f] += lr * g

    n_pairs = len(pairs)
    # Trust the learned signal more as pairs accumulate; ~0 at 0 pairs, ~0.8 at 20.
    learn_strength = round(min(0.8, n_pairs / 25.0), 3)
    blended = {
        f: round((1 - learn_strength) * priors.get(f, 0.0) + learn_strength * learned[f], 4)
        for f in FEATURES
    }
    return blended, n_pairs, learn_strength


# --- scoring a choice -------------------------------------------------------
@dataclass
class Judgement:
    option: str
    utility: float
    drivers: list[str]
    explanation: str


def _drivers(weights: dict[str, float], x: dict[str, float], top: int = 2) -> list[str]:
    contrib = sorted(
        ((f, weights.get(f, 0.0) * x.get(f, 0.0)) for f in FEATURES),
        key=lambda kv: abs(kv[1]), reverse=True,
    )
    out = []
    for f, c in contrib[:top]:
        if abs(c) < 1e-6:
            continue
        out.append(_AXIS_POS[f] if c > 0 else f"avoiding {_AXIS_NEG[f]}")
    return out


def decide(options: list[dict], weights: dict[str, float]) -> dict:
    """Score & rank options. Each option = {"name": str, **features in [0,1]}."""
    if not options:
        return {"ready": False, "message": "No options to weigh."}
    judged: list[Judgement] = []
    for opt in options:
        x = {f: float(opt.get(f, 0.0)) for f in FEATURES}
        u = round(_dot(weights, x), 4)
        drv = _drivers(weights, x)
        because = (" because it leans into " + " and ".join(drv)) if drv else ""
        judged.append(Judgement(opt.get("name", "?"), u, drv,
                                 f"{opt.get('name', '?')} scores {u:+.2f}{because}."))
    judged.sort(key=lambda j: j.utility, reverse=True)
    top = judged[0]
    margin = top.utility - judged[1].utility if len(judged) > 1 else top.utility
    lean = "clearly" if margin > 0.3 else "slightly" if margin > 0.08 else "barely"
    return {
        "ready": True,
        "recommendation": top.option,
        "lean": lean,
        "margin": round(margin, 4),
        "ranking": [j.__dict__ for j in judged],
    }


# --- readable profile -------------------------------------------------------
def value_profile(weights: dict[str, float], top: int = 4) -> list[str]:
    ranked = sorted(FEATURES, key=lambda f: abs(weights.get(f, 0.0)), reverse=True)
    out = []
    for f in ranked[:top]:
        wv = weights.get(f, 0.0)
        if abs(wv) < 0.03:
            continue
        out.append(_AXIS_POS[f] if wv > 0 else _AXIS_NEG[f])
    return out


# --- DB adapter -------------------------------------------------------------
def build(db) -> dict:
    """Learn the user's value profile from their real history."""
    from datetime import datetime, timezone

    from . import cognitive_model, decision_genome

    now = datetime.now(timezone.utc).isoformat()
    try:
        twin = cognitive_model.build(db)
        traits = twin.get("traits") or []
    except Exception:
        traits = []
    priors = trait_priors(traits)

    # Revealed preferences: each past project decision is an example whose value
    # is its follow-through; features describe the choice as it was made.
    examples: list[tuple[dict[str, float], float]] = []
    basis: list[dict] = []
    try:
        dg = decision_genome.build(db)
        decisions = dg.get("decisions") or [] if dg.get("ready") else []
    except Exception:
        decisions = []

    n = len(decisions)
    for idx, d in enumerate(decisions):
        # Newer starts are more "novel"/continuation-light; collaborative flips solo.
        recency = 1.0 - (idx / n) if n > 1 else 0.5  # decisions are outcome-sorted, not time — rough
        feats = {
            "novelty": 0.6,                       # a project start is an exploratory act
            "continuation": d.get("followthrough", 0.0),
            "alignment": min(1.0, d.get("longevity_weeks", 0) / 12.0),
            "solo": 0.0 if d.get("collaborative") else 1.0,
            "depth": d.get("followthrough", 0.0),
            "momentum": d.get("followthrough", 0.0),
            "goal_fit": 0.5,
        }
        value = d.get("followthrough", 0.0)
        examples.append((feats, value))
        basis.append({"subject": d.get("subject"), "outcome": d.get("outcome"),
                      "followthrough": d.get("followthrough")})

    weights, n_pairs, learn_strength = learn_weights(examples, priors)
    confidence = _conf(n_pairs, 25)
    profile = value_profile(weights)

    ready = bool(traits or n_pairs)
    return {
        "generated_at": now,
        "ready": ready,
        "note": ("How your second brain models what you value, learned from your own "
                 "behaviour. Lean on priors when data is thin; the learned signal grows "
                 "as you feed in more decisions."),
        "confidence": confidence,
        "data_basis": {
            "trait_count": len(traits),
            "decision_examples": len(examples),
            "comparison_pairs": n_pairs,
            "learned_vs_prior": learn_strength,
        },
        "value_profile": profile,
        "weights": weights,
        "summary": (
            "Right now your model is built " +
            (f"mostly from your traits (only {n_pairs} behavioural comparisons so far)."
             if learn_strength < 0.3 else
             f"from a blend of your traits and {n_pairs} behavioural comparisons.") +
            (" You tend to value " + ", ".join(profile) + "." if profile else "")
        ),
        "learned_from": basis,
    }
