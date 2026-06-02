"""Unit tests for the V2 cognitive cores (pure, DB-free).

These exercise the numerical/logic cores with synthetic behavioural data so they
can run without Postgres/pgvector. The DB adapters (simulate/detect/assess) are
thin wrappers verified separately once the database is available.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.life_sim import (  # noqa: E402
    project_trajectories, cf_daily_practice, cf_consistent_habit, cf_finish_projects,
    SCENARIOS, HORIZONS,
)
from app.chapters import detect_chapters  # noqa: E402
from app.identity import score_goal  # noqa: E402
from app.habit_genome import classify_habit  # noqa: E402
from app.decision_genome import classify_decision, decision_patterns  # noqa: E402
from app.blind_spots import (  # noqa: E402
    from_decisions, from_habits, from_identity, synthesize,
)
from app.personal_os import compose  # noqa: E402
from app.knowledge_graph import build_graph  # noqa: E402
from app.learning_model import model_concept, build_learning  # noqa: E402
from app.you_model import (  # noqa: E402
    trait_priors, learn_weights, decide, value_profile, FEATURES,
)
from app.self_model import extract_claims, reconcile  # noqa: E402


def test_self_model_extracts_claims_with_polarity():
    text = ("I work in bursts and can't show up daily. I keep starting things but I "
            "abandon them and restart. I'm emotionally reactive and easily distracted.")
    claims = {c.dimension: c for c in extract_claims(text)}
    assert "consistency" in claims and claims["consistency"].polarity < 0
    assert "follow_through" in claims and claims["follow_through"].polarity < 0
    assert claims["follow_through"].quote  # carries a supporting sentence
    print("self-claims:", {k: round(v.polarity, 2) for k, v in claims.items()})


def test_self_model_reconcile_flags_survivorship_divergence():
    # Self says "I never finish"; behaviour (git survivors) says high follow-through.
    text = "I abandon projects, I never finish anything, I just restart."
    claims = extract_claims(text)
    findings = reconcile(claims, {"followthrough": 0.8})
    div = next(f for f in findings if f.dimension == "follow_through")
    assert div.kind == "divergence"
    assert "survived into commits" in div.note  # surfaces the data bias
    print("divergence:", div.note)


def test_you_model_priors_reflect_traits():
    traits = [
        {"name": "curiosity", "label": "Highly curious", "score": 0.9},
        {"name": "focus", "label": "Deep focuser", "score": 0.85},
        {"name": "collaboration_preference", "label": "Independent", "score": 0.8},
    ]
    w = trait_priors(traits)
    assert w["novelty"] > 0.3      # high curiosity → values novelty
    assert w["depth"] > 0.3        # deep focuser → values depth
    assert w["solo"] > 0           # independent → prefers solo
    print("priors:", {k: round(v, 2) for k, v in w.items() if v})


def test_you_model_learns_from_revealed_preference():
    # Examples: high-continuation choices followed through, low ones didn't.
    base = {f: 0.0 for f in FEATURES}
    good = {**base, "continuation": 1.0, "momentum": 1.0}
    bad = {**base, "continuation": 0.0, "momentum": 0.0}
    examples = [(good, 0.9), (good, 0.85), (bad, 0.1), (bad, 0.05)]
    priors = {f: 0.0 for f in FEATURES}
    w, n_pairs, strength = learn_weights(examples, priors)
    assert n_pairs >= 4
    # It should have learned to reward continuation/momentum.
    assert w["continuation"] > 0 and w["momentum"] > 0
    print("learned:", {k: round(v, 2) for k, v in w.items() if abs(v) > 0.01}, "pairs:", n_pairs)


def test_you_model_decide_ranks_by_value():
    weights = {f: 0.0 for f in FEATURES}
    weights["continuation"] = 1.0   # this person values finishing what they started
    options = [
        {"name": "Finish PRL", "continuation": 0.9, "novelty": 0.1},
        {"name": "Start something new", "continuation": 0.0, "novelty": 0.9},
    ]
    out = decide(options, weights)
    assert out["ready"] and out["recommendation"] == "Finish PRL"
    assert out["ranking"][0]["utility"] > out["ranking"][1]["utility"]
    print("decision:", out["recommendation"], out["lean"], "margin", out["margin"])


def test_trajectories_cover_all_scenarios_and_horizons():
    weekly = [3, 4, 5, 6, 5, 7, 8, 9]      # rising activity
    skill_idle = [5, 40, 120, 200]          # one already-faded skill
    trs = project_trajectories(weekly, skill_idle)
    assert len(trs) == len(SCENARIOS) * len(HORIZONS)
    # Growth must out-project decline at every horizon.
    for hlabel, _ in HORIZONS:
        g = next(t for t in trs if t.scenario == "growth" and t.horizon == hlabel)
        d = next(t for t in trs if t.scenario == "decline" and t.horizon == hlabel)
        assert g.projected_activity > d.projected_activity
        assert g.skills_kept >= d.skills_kept
    # Longer horizons accumulate more activity within a scenario.
    steady = [t for t in trs if t.scenario == "steady"]
    by_h = {t.horizon: t.projected_activity for t in steady}
    assert by_h["5 years"] > by_h["1 year"] > by_h["90 days"] > by_h["30 days"]
    print("trajectories:", {t.horizon: t.projected_activity for t in steady})


def test_counterfactual_daily_practice_positive_delta():
    cf = cf_daily_practice([2, 3, 2, 4, 3], horizon_days=365)
    assert cf.alternative > cf.baseline
    assert cf.delta_pct > 0
    print("daily-practice CF:", cf.baseline, "->", cf.alternative, f"(+{cf.delta_pct}%)")


def test_counterfactual_consistent_habit_and_finish():
    cf1 = cf_consistent_habit([2, 5, 1, 3], horizon_days=365)
    assert cf1.alternative >= cf1.baseline
    cf2 = cf_finish_projects(neglected=3, completion_rate=2.0)
    assert cf2.alternative > cf2.baseline
    print("habit CF:", cf1.baseline, "->", cf1.alternative, "| finish CF:", cf2.baseline, "->", cf2.alternative)


def test_chapter_detection_merges_and_smooths():
    monthly = [
        ("2024-01", "School"), ("2024-02", "School"),
        ("2024-03", "ML"), ("2024-04", "School"), ("2024-05", "ML"),  # blip smoothing
        ("2024-06", "ML"), ("2024-07", "ML"),
        ("2024-08", "Research"), ("2024-09", "Research"),
    ]
    chapters = detect_chapters(monthly)
    themes = [c.theme for c in chapters]
    assert themes == ["School", "ML", "Research"], themes
    assert chapters[-1].end == "2024-09"
    print("chapters:", [(c.theme, c.span_months) for c in chapters])


def test_identity_alignment_flags_contradiction():
    # Claimed top priority, but only 3% of recent activity -> contradiction.
    weak = score_goal("Become ML Engineer", claim_strength=1.0, recent_activity=3, total_recent=100)
    assert weak.alignment == "weak" and weak.contradiction is True
    strong = score_goal("Ship PRL", claim_strength=0.8, recent_activity=40, total_recent=100)
    assert strong.alignment == "strong" and strong.contradiction is False
    print("identity:", weak.alignment, "(contradiction)", "|", strong.alignment)


def test_habit_lifecycle_stages():
    # Recently emerged + rising -> forming/growing; long idle -> dead/dormant.
    young = classify_habit("Daily Coding", [0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 3, 4])
    assert young.stage in ("forming", "growing"), young.stage
    dead = classify_habit("Reading", [4, 5, 3, 4, 0, 0, 0, 0, 0, 0, 0, 0])
    assert dead.stage in ("dead", "dormant"), dead.stage
    steady = classify_habit("Research", [3, 3, 4, 3, 3, 4, 3, 3, 4, 3, 3, 3])
    assert steady.stage == "stable", steady.stage
    print("habit stages:", young.stage, dead.stage, steady.stage)


def test_habit_outcome_correlation():
    weekly = [0, 1, 2, 3, 4, 5]
    prod = [1, 2, 3, 4, 5, 6]   # rises together -> positive correlation
    g = classify_habit("Exercise", weekly, prod)
    assert g.outcome_correlation >= 0.9, g.outcome_correlation
    print("habit corr:", g.outcome_correlation)


def test_decision_outcomes():
    abandoned = classify_decision([1, 1, 0, 0, 0, 0])
    assert abandoned[0] == "abandoned", abandoned
    thriving = classify_decision([2, 3, 2, 3, 2, 3, 2, 2])
    assert thriving[0] == "thriving", thriving
    stalled = classify_decision([3, 4, 2, 0, 0, 0, 0, 0])
    assert stalled[0] == "stalled", stalled
    print("decision outcomes:", abandoned[0], thriving[0], stalled[0])


def test_decision_patterns_detect_lift():
    # Collaborative decisions succeed more often than solo ones.
    decisions = [
        {"good": True, "collaborative": True, "busy_start": True},
        {"good": True, "collaborative": True, "busy_start": False},
        {"good": True, "collaborative": True, "busy_start": True},
        {"good": False, "collaborative": False, "busy_start": False},
        {"good": False, "collaborative": False, "busy_start": True},
        {"good": True, "collaborative": False, "busy_start": False},
    ]
    pats = decision_patterns(decisions)
    collab = next(p for p in pats if p.name == "collaborative")
    assert collab.success_with > collab.success_without
    assert collab.lift > 0
    print("decision pattern lift:", collab.success_with, "vs", collab.success_without, f"(+{collab.lift})")


def test_blind_spot_serial_starter_and_patterns():
    decisions = {
        "ready": True, "confidence": 0.7, "decision_count": 8, "followthrough_rate": 0.25,
        "outcome_counts": {"abandoned": 5, "stalled": 1, "sustained": 2},
        "patterns": [
            {"name": "busy_start", "observation": "Busy-start decisions follow through less.",
             "lift": -0.5, "confidence": 0.6},
            {"name": "collaborative", "observation": "Collaborative decisions thrive.",
             "lift": 0.4, "confidence": 0.6},
        ],
    }
    spots = from_decisions(decisions)
    kinds = {s.kind for s in spots}
    assert any(k == "serial_starter" for k in kinds)
    assert any(s.category == "risk" for s in spots)        # the antipattern
    assert any(s.category == "opportunity" for s in spots)  # the success condition
    print("decision blind spots:", [(s.category, s.kind) for s in spots])


def test_blind_spot_fading_and_hidden_driver():
    habits = {"ready": True, "confidence": 0.7, "habits": [
        {"name": "Reading", "stage": "dormant", "consistency": 0.7, "outcome_correlation": 0.1},
        {"name": "Coding", "stage": "stable", "consistency": 0.9, "outcome_correlation": 0.8},
    ]}
    spots = from_habits(habits)
    assert any(s.kind.startswith("fading_investment") for s in spots)
    assert any(s.kind.startswith("hidden_driver") for s in spots)
    print("habit blind spots:", [s.kind for s in spots])


def test_blind_spot_claim_gap_and_ranking():
    identity = {"ready": True, "confidence": 0.6, "alignments": [
        {"goal": "Become ML Engineer", "claim_strength": 1.0, "pursuit_share": 0.03,
         "contradiction": True, "explanation": "Claimed top priority, 3% of activity."},
    ]}
    out = synthesize(
        {"ready": True, "confidence": 0.7, "decision_count": 8, "followthrough_rate": 0.25,
         "outcome_counts": {"abandoned": 5}, "patterns": []},
        {"ready": False}, identity, {"predictions": []},
    )
    assert out["ready"] and out["blind_spots"]
    # Sorted by severity*confidence -> highest first.
    sev = [b["severity"] * b["confidence"] for b in out["blind_spots"]]
    assert sev == sorted(sev, reverse=True)
    assert any(b["category"] == "misalignment" for b in out["blind_spots"])
    print("synthesised blind spots:", out["category_counts"])


def test_personal_os_composes_navigation_map():
    model = {
        "summary": "This person is a hands-on builder, exploratory.",
        "maturity": 0.4,
        "traits": [{"label": "Hands-on builder", "score": 0.7}],
        "knowledge_distribution": [{"skill": "Python"}, {"skill": "FastAPI"}],
    }
    identity = {"ready": True, "confidence": 0.6, "alignments": [
        {"goal": "Become ML Engineer", "claim_strength": 1.0, "pursuit_share": 0.1,
         "contradiction": True, "explanation": "Claimed top priority, 10% of activity."},
        {"goal": "Ship PRL", "claim_strength": 0.6, "pursuit_share": 0.4,
         "contradiction": False, "explanation": "Actively pursued."},
    ]}
    blind = {"ready": True, "blind_spots": [
        {"category": "risk", "title": "Start more than you finish", "finding": "...", "severity": 0.7,
         "references": ["decision_genome"]},
        {"category": "opportunity", "title": "Hidden driver: Coding", "finding": "...", "severity": 0.8,
         "references": ["habit_genome"]},
    ]}
    sim = {"ready": True, "counterfactuals": [
        {"premise": "If you practised daily", "horizon": "365 days", "delta_pct": 150.0,
         "explanation": "..."},
    ]}
    habits = {"ready": True, "habits": [{"name": "Coding", "stage": "stable"}]}

    nav = compose(model, identity, blind, sim, habits)
    assert nav["ready"]
    # Desired goals sorted by priority; widest distance is the ML goal (1.0-0.1=0.9).
    assert nav["desired_state"]["goals"][0]["goal"] == "Become ML Engineer"
    assert nav["distance"]["per_goal"][0]["goal"] == "Become ML Engineer"
    assert nav["distance"]["per_goal"][0]["distance"] == 0.9
    # Obstacles include the risk; leverage includes the opportunity + counterfactual.
    assert any(o["title"] == "Start more than you finish" for o in nav["obstacles"])
    sources = {p["source"] for p in nav["leverage_points"]}
    assert {"blind_spots", "life_sim", "identity"} <= sources
    # Leverage sorted by impact desc.
    impacts = [p["impact"] for p in nav["leverage_points"]]
    assert impacts == sorted(impacts, reverse=True)
    print("personal OS:", "distance=", nav["distance"]["overall"],
          "obstacles=", len(nav["obstacles"]), "leverage=", len(nav["leverage_points"]))


def test_knowledge_graph_recovers_evolution_spine():
    # first_seen as day-offsets; the spec's chain co-occurs sequentially.
    chain = ["Python", "FastAPI", "Backend", "Fraud Detection", "ML", "Graph Intelligence", "PRL"]
    concepts = [{"name": n, "first_seen": i * 10, "weight": 1.0, "mentions": 5}
                for i, n in enumerate(chain)]
    cooccur = {}
    for i in range(len(chain) - 1):
        cooccur[(chain[i], chain[i + 1])] = 5  # strong sequential link
    # plus a weak distracting link that must NOT win the spine
    cooccur[("Python", "PRL")] = 1

    g = build_graph(concepts, cooccur)
    assert g["root"] == "Python" and g["leaf"] == "PRL"
    assert g["spine"] == chain, g["spine"]
    # Edges always point forward in time (DAG invariant).
    assert all(e["order_gap"] > 0 for e in g["edges"])
    print("knowledge spine:", " -> ".join(g["spine"]))


def test_learning_retention_decays_with_idle():
    fresh = model_concept("Python", reps=20, idle_days=2, span_days=300, recent_reps=8)
    stale = model_concept("Python", reps=20, idle_days=200, span_days=300, recent_reps=0)
    assert fresh.retention > stale.retention            # idle erodes retention
    assert fresh.knowledge_level == stale.knowledge_level  # depth already reached
    assert stale.half_life_days > 0
    print("retention fresh vs stale:", fresh.retention, stale.retention)


def test_learning_statuses():
    mastered = model_concept("FastAPI", reps=25, idle_days=3, span_days=250, recent_reps=6)
    assert mastered.status == "mastered", mastered.status
    forgotten = model_concept("Rust", reps=10, idle_days=240, span_days=120, recent_reps=0)
    assert forgotten.status == "forgotten", forgotten.status
    bottleneck = model_concept("Category Theory", reps=3, idle_days=1, span_days=20, recent_reps=12)
    assert bottleneck.status == "bottleneck", bottleneck.status
    print("statuses:", mastered.status, forgotten.status, bottleneck.status)


def test_learning_aggregate_sorts_and_buckets():
    out = build_learning([
        {"name": "FastAPI", "reps": 25, "idle_days": 3, "span_days": 250, "recent_reps": 6},
        {"name": "Rust", "reps": 10, "idle_days": 240, "span_days": 120, "recent_reps": 0},
    ])
    assert out["ready"] and out["concept_count"] == 2
    # Sorted most-at-risk (lowest retention) first.
    rets = [c["retention"] for c in out["concepts"]]
    assert rets == sorted(rets)
    assert "Rust" in out["forgotten"] and "FastAPI" in out["mastered"]
    print("learning buckets:", out["status_counts"])


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print(f"  ✓ {fn.__name__}")
    print(f"\n✅ {passed}/{len(fns)} V2 core tests passed")
