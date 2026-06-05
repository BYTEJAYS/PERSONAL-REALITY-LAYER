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
from datetime import date  # noqa: E402
from app.finance_cortex import Transaction, analyze as fin_analyze  # noqa: E402
from app.health_cortex import HealthEvent, analyze as health_analyze  # noqa: E402
from app.family_cortex import FamilyFact, analyze as family_analyze  # noqa: E402
from app.extract_life import extract_finance, extract_health, extract_family  # noqa: E402
from app.rhythm import best_window, window_center, rhythm_label  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402
from app.events import EventItem, cluster_events  # noqa: E402
from app.memory_aging import (  # noqa: E402
    AgingItem, age_tier, target_detail, raw_expired, retention_plan, effective_age,
)
from app.dedup import (  # noqa: E402
    DupItem, cosine, find_duplicate_groups, dedup_savings,
)
from app.patterns import (  # noqa: E402
    DayRecord, learn_pattern, find_exceptions, summarize as pat_summarize,
)
from app.fractal import LeafEvent, build_fractal, zoom  # noqa: E402
from app.compressor import (  # noqa: E402
    deterministic_summary, summarize_event, memory_dna, plan_compression, plan_stats,
)
from app.reconstructor import (  # noqa: E402
    deterministic_reconstruction, reconstruct_memory, reconstruction_fidelity,
)
from app.emotional_cortex import EmotionEvent, analyze as emo_analyze, valence  # noqa: E402
from app.social_cortex import Interaction, analyze as social_analyze  # noqa: E402
from app.behaviour_cortex import Activity, analyze as beh_analyze  # noqa: E402
from app.time_machine import TimePoint, bucket, in_period  # noqa: E402
from app.importance_engine import (  # noqa: E402
    ImportanceFactors, score_importance, label_for,
)
from app.confidence_engine import Evidence, score_confidence, source_quality  # noqa: E402
from app.memory_economy import memory_value, compression_policy, MemoryEcon  # noqa: E402
from app.versioning import VersionedFact, build_fact  # noqa: E402
from app.curiosity_engine import (  # noqa: E402
    detect_gaps, from_unidentified_people, from_repeated_topics,
    synthesize as curiosity_synthesize,
)
from app.reality_compiler import pipeline_report, STAGES  # noqa: E402
from app.world_model import assemble_world, domain_status  # noqa: E402
from app.agents import route, council, roster, AGENTS  # noqa: E402
from app.self_evolution import adapt_weights, learned_priorities, weight_shift  # noqa: E402
from app.provenance import build_provenance, audit_trail  # noqa: E402
from app.event_simulator import simulate, compare  # noqa: E402
from app.thought_capture import classify_capture  # noqa: E402
from app.companion import (  # noqa: E402
    mask_numbers, qualitative_money, redact_evidence, disclosure_policy,
    compose_friend_answer,
)
from app.auth import parse_tokens, classify_token  # noqa: E402


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


# --- Life-domain cortexes ---------------------------------------------------

def test_finance_detects_recurring_bill_and_next_due():
    txns = [
        Transaction(date(2026, 3, 5), 1200, category="utilities", merchant="electricity"),
        Transaction(date(2026, 4, 5), 1200, category="utilities", merchant="electricity"),
        Transaction(date(2026, 5, 5), 1200, category="utilities", merchant="electricity"),
        Transaction(date(2026, 5, 10), 50000, category="salary", kind="income"),
    ]
    out = fin_analyze(txns, today=date(2026, 5, 20))
    assert out["ready"]
    rec = out["recurring_payments"]
    assert any(r["payee"] == "electricity" and r["cadence"] == "monthly" for r in rec)
    bill = next(r for r in rec if r["payee"] == "electricity")
    assert bill["next_due"] == "2026-06-04"  # last paid 05-05 + ~30d
    assert out["savings_rate"] is not None and out["savings_rate"] > 0
    print("finance recurring:", bill["payee"], bill["cadence"], bill["next_due"])


def test_finance_flags_anomaly():
    txns = [Transaction(date(2026, 5, d), amt, category="food") for d, amt in
            [(1, 300), (3, 280), (5, 320), (7, 5000)]]
    out = fin_analyze(txns, today=date(2026, 5, 10))
    assert out["anomalies"], "should flag the 5000 food spend"
    assert out["anomalies"][0]["amount"] == 5000
    print("anomaly:", out["anomalies"][0]["note"])


def test_finance_extractor_parses_text():
    recs = extract_finance("Paid ₹1,200 for the electricity bill. Got my salary of ₹50000.",
                           date(2026, 5, 5))
    cats = {r["category"]: r for r in recs}
    assert "utilities" in cats and cats["utilities"]["amount"] == 1200
    assert any(r["kind"] == "income" and r["amount"] == 50000 for r in recs)
    print("finance extract:", [(r["amount"], r["category"], r["kind"]) for r in recs])


def test_health_meds_visits_and_checkup_reminder():
    evs = [
        HealthEvent(date(2025, 1, 10), "prescription", "metformin", doctor="Sharma"),
        HealthEvent(date(2025, 1, 10), "visit", "Sharma", doctor="Sharma"),
        HealthEvent(date(2026, 5, 1), "test", "blood sugar", value=110, unit="mg/dl"),
        HealthEvent(date(2026, 5, 1), "test", "blood sugar", value=140, unit="mg/dl"),
    ]
    out = health_analyze(evs, today=date(2026, 6, 1))
    assert out["ready"]
    sugar = next(t for t in out["test_trends"] if t["name"] == "blood sugar")
    assert sugar["direction"] == "rising"
    assert any(r["type"] == "checkup_due" for r in out["reminders"])  # last visit > 180d
    print("health:", sugar["direction"], [r["type"] for r in out["reminders"]])


def test_health_extractor_parses_text():
    recs = extract_health("Dr. Sharma prescribed metformin. My blood sugar was 140 mg/dL.",
                          date(2026, 5, 1))
    kinds = {r["kind"] for r in recs}
    assert "prescription" in kinds and "test" in kinds
    test = next(r for r in recs if r["kind"] == "test")
    assert test["value"] == 140 and "metformin" in {r["name"] for r in recs}
    print("health extract:", [(r["kind"], r["name"], r["value"]) for r in recs])


def test_family_important_date_next_occurrence_and_reminder():
    facts = [
        FamilyFact(date(2026, 6, 1), "mother", "mother", "date", "birthday", recur_month=6, recur_day=5),
        FamilyFact(date(2026, 6, 1), "grandmother", "grandmother", "recipe", "her biryani recipe"),
    ]
    out = family_analyze(facts, today=date(2026, 6, 1))
    assert out["ready"]
    bday = out["important_dates"][0]
    assert bday["next_occurrence"] == "2026-06-05" and bday["days_until"] == 4
    assert out["reminders"] and out["reminders"][0]["type"] == "upcoming_date"
    assert any(s["kind"] == "recipe" for s in out["stories"])
    print("family date:", bday["occasion"], bday["next_occurrence"], "reminder:", out["reminders"][0]["detail"])


def test_family_extractor_parses_relations_and_dates():
    recs = extract_family("My mother's birthday is on June 5. Grandmother used to tell me stories.",
                          date(2026, 6, 1))
    kinds = {r["kind"] for r in recs}
    assert "date" in kinds and "story" in kinds
    d = next(r for r in recs if r["kind"] == "date")
    assert d["recur_month"] == 6 and d["recur_day"] == 5 and d["relation"] == "mother"
    print("family extract:", [(r["relation"], r["kind"]) for r in recs])


# --- Life-domain cortexes: robustness / precision -------------------------

def test_cortexes_empty_inputs_are_graceful():
    assert fin_analyze([])["ready"] is False
    assert health_analyze([])["ready"] is False
    assert family_analyze([])["ready"] is False
    print("empty cortex inputs handled")


def test_finance_extractor_no_false_positives_on_plain_numbers():
    # No currency symbol/word → must NOT be read as money.
    recs = extract_finance("I have 3 meetings and finished 2 tasks at 5pm.", date(2026, 5, 1))
    assert recs == [], recs
    print("finance false-positive guard ok")


def test_health_extractor_ignores_bp_ratio():
    # Blood pressure is a ratio, not a single trendable value — must be skipped.
    recs = extract_health("My BP was 120/80 today.", date(2026, 5, 1))
    assert all(r["name"] != "bp" for r in recs), recs
    print("bp ratio correctly skipped:", recs)


def test_health_canonicalises_sugar_alias():
    recs = extract_health("glucose 99 mg/dl", date(2026, 5, 1))
    assert any(r["name"] == "blood sugar" and r["value"] == 99 for r in recs), recs
    print("sugar alias canonicalised")


def test_family_extractor_ignores_unrelated_sentences():
    recs = extract_family("I deployed the server and fixed a bug.", date(2026, 6, 1))
    assert recs == [], recs
    print("family extractor precision ok")


# --- Rhythm: the reconciled time-of-day definition ------------------------

def test_rhythm_best_window_finds_night_block_and_wraps():
    w = [0.0] * 24
    for h in (22, 23, 0, 1):   # activity clustered around midnight
        w[h] = 5.0
    start, end, share = best_window(w, 4)
    assert start == 22 and end == 2          # wraps midnight
    assert share > 0.9
    print("night window:", start, end, share)


def test_rhythm_label_thresholds():
    assert rhythm_label(23) == "Night owl"
    assert rhythm_label(2) == "Night owl"
    assert rhythm_label(8) == "Early bird"
    assert rhythm_label(13) == "Afternoon"
    assert rhythm_label(19) == "Evening"


def test_rhythm_twin_and_pattern_engine_agree():
    # The whole point of the reconciliation: the trait label (from the window
    # centre) and the peak window (same function) describe the SAME time of day.
    w = [0.0] * 24
    for h in (22, 23, 0, 1):
        w[h] = 5.0
    start, end, _ = best_window(w, 4)         # what pattern_engine reports
    label = rhythm_label(window_center(start, 4))  # what cognitive_model reports
    assert label == "Night owl"               # consistent story, not contradictory
    assert 22 <= start or start <= 2
    print("reconciled:", f"{start:02d}-{end:02d}", "->", label)


def test_rhythm_empty_is_safe():
    assert best_window([0.0] * 24, 4) == (0, 4, 0.0)   # no crash, zero share


# --- Memory-Architecture V3: Event-Centric Memory --------------------------
def _utc(y, m, d, h=12):
    return datetime(y, m, d, h, tzinfo=timezone.utc)


def test_events_collapse_same_day_burst_into_one():
    # A wedding day: many memories, same people, same day -> ONE event.
    items = [
        EventItem(f"w{i}", _utc(2025, 12, 14, 9 + i), f"Wedding moment {i}",
                  entities=("Sister", "Home"), importance=0.6 + 0.05 * i)
        for i in range(6)
    ]
    events = cluster_events(items)
    assert len(events) == 1
    ev = events[0]
    assert ev.size == 6
    assert "Sister" in ev.people
    assert ev.span_days == 0
    print("event:", ev.title, "size", ev.size, "people", ev.people)


def test_events_split_unrelated_distant_memories():
    items = [
        EventItem("a", _utc(2025, 1, 1), "Random Tuesday", importance=0.3),
        EventItem("b", _utc(2025, 6, 1), "Months later", importance=0.3),
        EventItem("c", _utc(2025, 12, 1), "Even later", importance=0.3),
    ]
    events = cluster_events(items)
    assert len(events) == 3  # no shared entity, big gaps -> separate events


def test_events_bridge_shared_entity_across_weeks():
    # Same project resurfacing over 3 weeks bridges into one event despite gaps.
    items = [
        EventItem("p1", _utc(2025, 3, 1), "Start PRL", entities=("prl",), importance=0.5),
        EventItem("p2", _utc(2025, 3, 12), "PRL again", entities=("prl",), importance=0.5),
        EventItem("p3", _utc(2025, 3, 25), "PRL more", entities=("prl",), importance=0.5),
    ]
    events = cluster_events(items)
    assert len(events) == 1
    assert events[0].span_days == 24


def test_events_empty_is_safe():
    assert cluster_events([]) == []


# --- Memory-Architecture V3: Memory Aging / Forgetting ---------------------
def test_aging_tiers_progress_with_age():
    assert age_tier(5, 0.5) == "full"
    assert age_tier(200, 0.5) == "summary"
    assert age_tier(3 * 365, 0.5) == "story"
    assert age_tier(30 * 365, 0.1) == "faded"
    # detail strictly decreases as memories get older
    assert target_detail(5, 0.5) > target_detail(200, 0.5) > target_detail(3 * 365, 0.5)


def test_aging_importance_resists_forgetting():
    # Same age, higher importance -> younger effective age -> richer tier.
    age = 3 * 365
    assert effective_age(age, 0.9) < effective_age(age, 0.1)
    assert target_detail(age, 0.95) >= target_detail(age, 0.05)


def test_raw_layer0_expires_by_importance():
    assert raw_expired(60, 0.1) is True       # trivial raw file past ~1 month
    assert raw_expired(60, 0.95) is False      # important raw file still inside ~6 months
    assert raw_expired(400, 0.95) is True      # nothing raw survives past the window


def test_retention_plan_reports_compression():
    items = [AgingItem("recent", 5, 0.5)] + [AgingItem(f"old{i}", 6 * 365, 0.2) for i in range(9)]
    plan = retention_plan(items)
    assert plan["count"] == 10
    assert plan["tiers"]["full"] == 1
    assert plan["compression_ratio"] < 1.0     # old memories compress the set
    print("aging plan:", plan["tiers"], "ratio", plan["compression_ratio"])


# --- Memory-Architecture V3: Duplicate Elimination -------------------------
def test_cosine_basic():
    assert round(cosine([1, 0], [1, 0]), 6) == 1.0
    assert round(cosine([1, 0], [0, 1]), 6) == 0.0


def test_dedup_collapses_near_identical():
    base = [1.0, 0.0, 0.0, 0.0]
    items = [
        DupItem("master", base, importance=0.9, ts=_utc(2025, 1, 1), title="Best shot"),
        DupItem("d1", [0.99, 0.01, 0.0, 0.0], importance=0.4, ts=_utc(2025, 1, 1, 13)),
        DupItem("d2", [0.98, 0.0, 0.02, 0.0], importance=0.4, ts=_utc(2025, 1, 1, 14)),
        DupItem("unique", [0.0, 0.0, 0.0, 1.0], importance=0.5, ts=_utc(2025, 2, 1)),
    ]
    groups = find_duplicate_groups(items, threshold=0.9)
    assert len(groups) == 1
    g = groups[0]
    assert g.size == 3
    assert g.master_id == "master"            # highest importance wins
    assert "unique" not in g.member_ids
    savings = dedup_savings(len(items), groups)
    assert savings["redundant_copies"] == 2
    print("dedup:", g.as_dict(), savings)


def test_dedup_no_false_positive_on_distinct():
    items = [
        DupItem("a", [1.0, 0.0, 0.0]),
        DupItem("b", [0.0, 1.0, 0.0]),
        DupItem("c", [0.0, 0.0, 1.0]),
    ]
    assert find_duplicate_groups(items, threshold=0.9) == []


# --- Memory-Architecture V3: Pattern + Exception storage -------------------
def test_patterns_learns_routine_and_flags_only_exceptions():
    routine = frozenset({"src:git", "type:knowledge"})
    days = [DayRecord(f"2026-01-{d:02d}", routine, 4) for d in range(1, 21)]
    # One trip day (novel tag) and one surge day.
    days.append(DayRecord("2026-01-21", frozenset({"ent:Goa", "type:episodic"}), 5))
    days.append(DayRecord("2026-01-22", routine, 40))
    pattern = learn_pattern(days)
    assert "src:git" in pattern.core_tags
    exc = {e.date: e for e in find_exceptions(days, pattern)}
    assert exc["2026-01-21"].kind == "novel"     # the Goa trip
    assert exc["2026-01-22"].kind == "surge"      # the unusually busy day
    assert "2026-01-05" not in exc                # ordinary routine days stored once, not per-day
    print("exceptions:", {k: v.kind for k, v in exc.items()})


def test_patterns_compression_beats_storing_every_day():
    routine = frozenset({"src:git"})
    days = [DayRecord(f"2026-02-{d:02d}", routine, 3) for d in range(1, 29)]
    out = pat_summarize(days)
    assert out["stored_units"] == 1               # just the pattern, no exceptions
    assert out["compression_ratio"] < 0.1         # 1 unit vs 28 days


def test_patterns_empty_is_safe():
    out = pat_summarize([])
    assert out["ready"] is False and out["compression_ratio"] == 0.0


# --- Memory-Architecture V3: Fractal Memory --------------------------------
def test_fractal_rolls_events_into_life_era_year():
    events = [
        LeafEvent(_utc(2019, 5, 1), "School play", theme="School", importance=0.5),
        LeafEvent(_utc(2021, 9, 1), "Start college", theme="College", importance=0.7),
        LeafEvent(_utc(2022, 3, 1), "Hackathon", theme="College", importance=0.6),
        LeafEvent(_utc(2025, 12, 14), "Sister's wedding", theme="Family", importance=0.95),
    ]
    root = build_fractal(events, era_years=5)
    assert root is not None and root.level == "life"
    assert root.size == 4
    assert root.top_title == "Sister's wedding"   # peak-importance descendant bubbles up
    eras = zoom(root, "era")
    assert len(eras) == 3                          # 2015–2019, 2020–2024, 2025–2029 buckets
    years = zoom(root, "year")
    assert {y["label"] for y in years} == {"2019", "2021", "2022", "2025"}
    print("eras:", [e["label"] for e in eras])


def test_fractal_empty_is_safe():
    assert build_fractal([]) is None
    assert zoom(None, "year") == []


# --- Memory-Architecture V3: Semantic Compression Executor -----------------
def _sample_event():
    return {
        "title": "Sister, Home · Dec 2025",
        "start": "2025-12-14T09:00:00+00:00",
        "end": "2025-12-15T22:00:00+00:00",
        "span_days": 1,
        "size": 6,
        "importance": 0.95,
        "people": ["Sister", "Home"],
        "highlights": ["Ceremony", "Reception", "Dance performance"],
        "memory_ids": ["m1", "m2", "m3", "m4", "m5", "m6"],
    }


def test_compressor_deterministic_summary_uses_only_given_facts():
    s = deterministic_summary(_sample_event())
    assert "6 memories" in s and "Sister" in s and "Ceremony" in s
    assert s.endswith(".")


def test_compressor_prefers_llm_then_falls_back():
    ev = _sample_event()
    # A working "model": echoes a vivid line.
    summary, by = summarize_event(ev, complete_fn=lambda s, u: "A joyful wedding day.")
    assert by == "llm" and summary == "A joyful wedding day."
    # Model unreachable (returns None) -> deterministic fallback, never crashes.
    summary2, by2 = summarize_event(ev, complete_fn=lambda s, u: None)
    assert by2 == "deterministic" and "memories" in summary2
    # No model at all -> deterministic.
    _, by3 = summarize_event(ev, complete_fn=None)
    assert by3 == "deterministic"


def test_compressor_memory_dna_is_compact_and_stable():
    ev = _sample_event()
    dna = memory_dna(ev, "A joyful wedding day.")
    assert dna["people"] == ["Sister", "Home"]
    assert dna["size"] == 6 and dna["summary"] == "A joyful wedding day."
    assert len(dna["highlights"]) <= 3
    # Same event -> same DNA code (deterministic identity).
    assert dna["code"] == memory_dna(ev, "different summary text")["code"]


def test_compressor_plan_collapses_events_and_dups():
    events = [_sample_event(), {"memory_ids": ["solo"], "size": 1}]  # solo is left alone
    dups = [{"master_id": "best", "member_ids": ["d1", "d2"], "avg_similarity": 0.99}]
    actions = plan_compression(events, dups, complete_fn=None)
    kinds = sorted(a.kind for a in actions)
    assert kinds == ["dedup_merge", "event_summary"]
    ev_action = next(a for a in actions if a.kind == "event_summary")
    assert ev_action.anchor == "m1" and ev_action.absorbs == ["m2", "m3", "m4", "m5", "m6"]
    stats = plan_stats(actions, total_memories=10)
    assert stats["memories_absorbed"] == 7      # 5 event members + 2 dup copies
    assert 0 < stats["compaction_ratio"] <= 1
    print("compaction plan:", stats)


def test_compressor_plan_empty_is_safe():
    assert plan_compression([], [], None) == []
    assert plan_stats([], 0)["compaction_ratio"] == 0.0


# --- Memory-Architecture V3: Generative Reconstruction ---------------------
def _sample_dna():
    return memory_dna(_sample_event(), "A joyful winter wedding at home.")


def test_reconstruction_roundtrips_from_dna():
    # Compress an event to DNA, then reconstruct from ONLY that DNA.
    dna = _sample_dna()
    out = reconstruct_memory(dna, complete_fn=None)
    assert out["is_reconstruction"] is True
    assert out["generated_by"] == "deterministic"
    assert "Sister" in out["narrative"]            # preserved people survive the round-trip
    assert "wedding" in out["narrative"].lower()   # preserved summary survives
    assert "Dec 2025" in out["title"]
    print("reconstruction:", out["narrative"])


def test_reconstruction_prefers_llm_then_falls_back():
    dna = _sample_dna()
    out = reconstruct_memory(dna, complete_fn=lambda s, u: "I remember the warmth of that day.")
    assert out["generated_by"] == "llm" and "warmth" in out["narrative"]
    # Model returns nothing -> deterministic, still labelled a reconstruction.
    out2 = reconstruct_memory(dna, complete_fn=lambda s, u: None)
    assert out2["generated_by"] == "deterministic" and out2["is_reconstruction"]


def test_reconstruction_fidelity_tracks_preserved_signal():
    rich = _sample_dna()
    sparse = memory_dna({"size": 1, "people": [], "highlights": [], "importance": 0.1}, "")
    assert reconstruction_fidelity(rich) > reconstruction_fidelity(sparse)
    assert 0.0 <= reconstruction_fidelity(sparse) <= 1.0


def test_reconstruction_empty_dna_is_safe():
    out = reconstruct_memory({}, complete_fn=None)
    assert out["fidelity"] == 0.0
    assert "No preserved essence" in out["narrative"]
    assert deterministic_reconstruction({})  # does not crash


# --- Cortexes V3: Emotional / Social / Behaviour ---------------------------
def test_emotional_cortex_reads_mood_and_rising_stress():
    now = _utc(2026, 6, 5)
    # Mostly positive history, then a recent stressful cluster.
    events = [EmotionEvent(_utc(2026, 1, d), "joy", 0.6) for d in range(1, 20)]
    events += [EmotionEvent(_utc(2026, 6, d), "stress", 0.7) for d in range(1, 5)]
    out = emo_analyze(events, today=now)
    assert out["ready"] and out["mood"] == "positive"   # history dominates overall
    assert out["stress"]["rising"] is True               # but recent window spikes
    assert valence("joy") > 0 > valence("stress")
    print("emotional:", out["mood"], "rising:", out["stress"]["rising"])


def test_emotional_cortex_empty_is_safe():
    assert emo_analyze([])["ready"] is False


def test_social_cortex_ranks_closeness_and_flags_drift():
    now = _utc(2026, 6, 5)
    events = [Interaction("Mom", _utc(2026, 6, d), 0.8) for d in range(1, 5)]      # frequent+recent
    events += [Interaction("OldFriend", _utc(2025, 1, d), 0.5) for d in range(1, 4)]  # gone quiet
    out = social_analyze(events, today=now)
    assert out["ready"] and out["inner_circle"][0] == "Mom"
    drift_names = {d["person"] for d in out["drifting"]}
    assert "OldFriend" in drift_names                     # >120d since last seen
    print("social:", out["inner_circle"], "drifting:", list(drift_names))


def test_behaviour_cortex_focus_window_uses_shared_rhythm():
    now = _utc(2026, 6, 5)
    acts = []
    for day in range(1, 15):
        for hr in (22, 23, 0, 1):                          # consistent night activity
            acts.append(Activity(_utc(2026, 5, day, hr), 0.6, "git"))
    out = beh_analyze(acts, today=now)
    assert out["ready"] and out["focus_window"]["label"] == "Night owl"
    assert out["active_days"] == 14
    assert 0 < out["consistency"] <= 1
    print("behaviour:", out["focus_window"], "consistency", out["consistency"])


def test_behaviour_cortex_empty_is_safe():
    assert beh_analyze([])["ready"] is False


# --- Time Machine ----------------------------------------------------------
def test_time_machine_buckets_each_scale():
    pts = [
        TimePoint(_utc(2019, 5, 1), "School play", 0.5),
        TimePoint(_utc(2025, 12, 14), "Sister's wedding", 0.95),
        TimePoint(_utc(2025, 12, 15), "Reception", 0.7),
    ]
    decades = bucket(pts, "decade")
    assert {d["key"] for d in decades} == {"2010s", "2020s"}
    months = bucket(pts, "month")
    dec25 = next(m for m in months if m["key"] == "2025-12")
    assert dec25["count"] == 2 and dec25["headline"] == "Sister's wedding"  # peak bubbles up
    years = bucket(pts, "year")
    assert years[0]["key"] == "2025"                       # newest first
    assert len(in_period(pts, "year", "2025")) == 2
    print("timemachine decades:", [d["key"] for d in decades])


def test_time_machine_empty_and_bad_scale():
    assert bucket([], "year") == []
    try:
        bucket([], "century")
        assert False, "expected ValueError"
    except ValueError:
        pass


# --- Reality OS: Importance Engine -----------------------------------------
def test_importance_marriage_beats_meme():
    marriage = score_importance(ImportanceFactors(
        emotional=1.0, relationship=1.0, financial=0.8, historical=1.0,
        frequency=1.0, rarity=1.0))
    meme = score_importance(ImportanceFactors(
        emotional=0.1, relationship=0.0, financial=0.0, historical=0.1,
        frequency=0.0, rarity=0.0))
    assert marriage["score"] > meme["score"]
    assert marriage["label"] == "Very High" and meme["label"] == "Low"
    assert marriage["drivers"]            # names what mattered
    print("importance:", marriage["label"], "vs", meme["label"])


def test_importance_labels_and_clamping():
    assert label_for(0.9) == "Very High" and label_for(0.0) == "Low"
    # Out-of-range factors are clamped, score stays in [0,1].
    s = score_importance(ImportanceFactors(emotional=5.0, rarity=-2.0))
    assert 0.0 <= s["score"] <= 1.0


# --- Reality OS: Confidence Engine -----------------------------------------
def test_confidence_more_distinct_sources_raise_trust():
    one = score_confidence(Evidence(sources=["note"]))
    many = score_confidence(Evidence(sources=["invoice", "bank", "photo"], verified=True))
    assert many["confidence"] > one["confidence"]
    assert many["label"] == "high"
    assert source_quality("invoice") > source_quality("chat")
    print("confidence:", one["confidence"], "->", many["confidence"])


def test_confidence_quarantines_unverified():
    none = score_confidence(Evidence(sources=[]))
    assert none["quarantine"] is True and none["confidence"] == 0.0
    weak = score_confidence(Evidence(sources=["inferred"]))
    assert weak["quarantine"] is True          # below threshold -> not trusted to long-term


# --- Reality OS: Memory Economy --------------------------------------------
def test_memory_economy_value_and_policy():
    high = memory_value(importance=0.9, confidence=0.9, relationship_weight=0.8, storage_cost=0.1)
    low = memory_value(importance=0.1, confidence=0.4, relationship_weight=0.0, storage_cost=1.0)
    assert high > low
    assert compression_policy(high) == "keep_full"
    assert compression_policy(low) in ("aggressive_compress", "drop")
    econ = MemoryEcon("m1", 0.9, 0.9, 0.8, 0.1).evaluate()
    assert econ["policy"] == "keep_full" and econ["memory_id"] == "m1"
    print("economy:", high, compression_policy(high), "|", low, compression_policy(low))


# --- Reality OS: Memory Versioning -----------------------------------------
def test_versioning_keeps_temporal_truth():
    fact = build_fact("favourite_language", [
        ("Python", "2019-01-01"),
        ("Rust", "2025-01-01"),
        ("Julia", "2033-01-01"),
    ])
    assert fact.current() == "Julia"
    assert fact.value_at("2021-06-01") == "Python"     # what was true THEN
    assert fact.value_at("2026-01-01") == "Rust"
    assert len(fact.versions) == 3
    # Previous versions get closed off, never overwritten.
    assert fact.timeline()[0]["valid_to"] is not None
    print("versioning:", [v["value"] for v in fact.timeline()])


def test_versioning_ignores_unchanged_repeats():
    fact = VersionedFact("city")
    fact.record("Delhi", "2020-01-01")
    fact.record("Delhi", "2021-01-01")   # same value -> no new version
    assert len(fact.versions) == 1


# --- Reality OS: Curiosity Engine ------------------------------------------
def test_curiosity_detects_gaps_and_asks():
    gaps = detect_gaps([2008, 2009, 2015, 2016])     # 2010-2014 missing
    assert gaps == [(2010, 2014)]
    qs = from_unidentified_people([{"name": "Riya", "mentions": 8, "identified": False}])
    assert qs and qs[0].kind == "identify" and "Riya" in qs[0].text
    health = from_repeated_topics([{"name": "Dr Sharma", "mentions": 6, "kind": "health"}])
    assert health and health[0].kind == "health"


def test_curiosity_synthesize_sorts_by_priority():
    qs = curiosity_synthesize(
        people=[{"name": "X", "mentions": 10, "identified": False}],
        topics=[{"name": "PRL", "mentions": 9, "kind": "project"}],
        years=[2010, 2020],
    )
    assert qs == sorted(qs, key=lambda q: -q.priority)
    assert any(q.kind == "gap" for q in qs)          # the 2011-2019 hole surfaced


# --- Reality OS: Reality Compiler ------------------------------------------
def test_reality_compiler_reports_reductions():
    counts = {"raw": 1000, "features": 1000, "entities": 200, "events": 120,
              "patterns": 30, "knowledge": 24, "meaning": 12, "wisdom": 6}
    rep = pipeline_report(counts)
    assert [s["stage"] for s in rep["stages"]] == list(STAGES)
    assert rep["overall_compaction"] == round(1 - 6 / 1000, 4)
    # entities stage is a big reduction from raw/features.
    ent = next(s for s in rep["stages"] if s["stage"] == "entities")
    assert ent["reduction_from_prev"] > 0.5
    print("compiler compaction:", rep["overall_compaction"])


def test_reality_compiler_empty_is_safe():
    rep = pipeline_report({})
    assert rep["overall_compaction"] == 0.0
    assert all(s["count"] == 0 for s in rep["stages"])


# --- Reality OS partials: Personal World Model -----------------------------
def test_world_model_assembles_and_flags_neglect():
    world = assemble_world({
        "health": {"score": 0.8, "summary": "active"},
        "finance": {"score": 0.5},
        "social": {"score": 0.15},          # neglected
        # emotional/behaviour/etc. missing -> unknown
    })
    assert domain_status(0.8) == "thriving"
    assert domain_status(0.3) == "at_risk" and domain_status(0.15) == "neglected"
    assert "health" in world["thriving"]
    assert "social" in world["neglected"]
    assert world["domains_known"] == 3 and world["domains_total"] == 9
    assert 0 <= world["coherence"] <= 1
    print("world coherence:", world["coherence"], "neglected:", world["neglected"])


# --- Reality OS partials: Multi-Agent Society ------------------------------
def test_agents_route_to_specialists():
    fin = route("how much money did I spend on bills?")
    assert fin and fin[0].name == "Finance"
    mood = route("why do I feel so stressed lately?")
    assert any(a.name == "Psychologist" for a in mood)
    # Unmatched query still convenes a non-empty senior council.
    panel = council("xyzzy nonsense")
    assert len(panel) == 3
    assert len(roster()) == len(AGENTS)


# --- Reality OS partials: Self-Evolution -----------------------------------
def test_self_evolution_shifts_weights_toward_preference():
    # User consistently treats relationship-heavy memories as important.
    examples = []
    for _ in range(20):
        examples.append(({"emotional": 0.1, "relationship": 1.0, "financial": 0.0,
                          "historical": 0.1, "frequency": 0.1, "rarity": 0.1}, 1.0))
        examples.append(({"emotional": 0.1, "relationship": 0.0, "financial": 0.1,
                          "historical": 0.1, "frequency": 0.1, "rarity": 0.1}, 0.0))
    evolved = adapt_weights(examples)
    assert abs(sum(evolved.values()) - 1.0) < 1e-6        # stays a valid distribution
    assert "relationship" in learned_priorities(evolved)   # learned what they value
    assert weight_shift(dict.fromkeys(evolved, 0.0), evolved)["relationship"] > 0


def test_self_evolution_no_data_keeps_priors():
    from app.importance_engine import WEIGHTS
    evolved = adapt_weights([])
    assert abs(sum(evolved.values()) - 1.0) < 1e-6
    # With no examples it returns the (normalised) base weights unchanged in rank.
    assert learned_priorities(evolved)[0] == learned_priorities(_normalise_like(WEIGHTS))[0]


def _normalise_like(w):
    s = sum(w.values())
    return {k: v / s for k, v in w.items()}


# --- Reality OS partials: Source Attribution -------------------------------
def test_provenance_auditable_needs_two_distinct_sources():
    single = build_provenance([{"type": "note", "ref": "n1", "ts": "2025-01-01"}])
    assert single["auditable"] is False
    multi = build_provenance([
        {"type": "invoice", "ref": "i1", "ts": "2028-03-01"},
        {"type": "bank", "ref": "b1", "ts": "2028-03-02"},
    ])
    assert multi["auditable"] is True and multi["distinct_types"] == 2
    assert "invoice" in audit_trail(multi)
    assert build_provenance([])["auditable"] is False
    print("provenance:", multi["summary"])


# --- Reality OS partials: Event Simulator ----------------------------------
def test_event_simulator_projects_tradeoffs():
    state = {"finance": 0.6, "social": 0.6, "behaviour": 0.6, "emotional": 0.6,
             "projects": 0.4, "knowledge": 0.5, "health": 0.6}
    res = simulate(state, "start_company")
    assert res["ready"]
    assert "projects" in res["gains"] and "finance" in res["losses"]
    assert res["after"]["projects"] > res["before"]["projects"]
    # Ranking favours higher confidence-weighted benefit.
    ranked = compare(state)
    assert ranked and ranked == sorted(ranked, key=lambda r: -r["score"])
    assert simulate(state, "nope")["ready"] is False
    print("simulate ranks:", [r["scenario"] for r in ranked[:3]])


# --- Reality OS partials: Dream/Thought Capture ----------------------------
def test_thought_capture_classifies_kinds_and_goals():
    assert classify_capture("I dreamt I was flying over the sea")["kind"] == "dream"
    assert classify_capture("What if memory could be compiled?")["kind"] == "question"
    todo = classify_capture("Need to call the bank today")
    assert todo["kind"] == "todo" and todo["urgency"] == "high"
    amb = classify_capture("I want to build a company that preserves human memory")
    assert amb["kind"] == "ambition" and amb["goal"]
    assert classify_capture("")["kind"] == "empty"
    print("capture goal:", amb["goal"])


# --- Companion mode: discretion / redaction --------------------------------
def test_companion_masks_money_and_medical_numbers():
    assert "[an amount]" in mask_numbers("spent ₹1,40,000 on a laptop")
    assert "[a reading]" in mask_numbers("blood sugar was 96 mg/dL")
    assert "[a number]" in mask_numbers("account 42317 balance")
    # Ordinary words untouched.
    assert "happy" in mask_numbers("he felt happy today")


def test_companion_redacts_private_and_sensitive():
    rows = [
        {"source": "self-analysis", "title": "raw", "content": "brutal private truth",
         "meta": {}},
        {"source": "bank", "title": "Salary ₹90,000", "content": "credited 90000",
         "meta": {"finance": [{"amount": 90000}]}},
    ]
    safe = redact_evidence(rows)
    # Private reflection: words never exposed.
    assert "brutal private truth" not in safe[0]["content"]
    assert safe[0]["title"] == "(a private reflection)"
    # Finance: numbers masked + raw finance meta stripped.
    assert "90,000" not in safe[1]["title"] and "90000" not in safe[1]["content"]
    assert "finance" not in safe[1]["meta"]


def test_companion_money_stays_qualitative():
    assert "comfortable" in qualitative_money(0.3, "steady")
    assert "stretched" in qualitative_money(0.0, "rising") or "tight" in qualitative_money(0.0, "rising")
    # Never leaks a figure.
    for sr in (None, 0.0, 0.1, 0.5):
        assert not any(ch.isdigit() for ch in qualitative_money(sr, "steady"))


def test_companion_policy_and_fallback_are_safe():
    pol = disclosure_policy()
    assert "Never state exact money" in pol and "private journal" in pol
    ans = compose_friend_answer("how is he?", [{"title": "trip to the hills"}], mood="content")
    assert "Jay" in ans and "content" in ans


# --- Companion mode: token auth --------------------------------------------
def test_auth_token_roles():
    friends = parse_tokens("alice123, bob456 ,")
    assert friends == {"alice123", "bob456"}
    assert classify_token("owner-secret", "owner-secret", friends) == "owner"
    assert classify_token("alice123", "owner-secret", friends) == "friend"
    assert classify_token("stranger", "owner-secret", friends) is None
    assert classify_token(None, "owner-secret", friends) is None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print(f"  ✓ {fn.__name__}")
    print(f"\n✅ {passed}/{len(fns)} V2 core tests passed")
