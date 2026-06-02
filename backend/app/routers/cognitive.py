from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import (
    blind_spots,
    chapters,
    cognitive_model,
    decision_genome,
    habit_genome,
    identity,
    knowledge_graph,
    learning_model,
    life_sim,
    pattern_engine,
    personal_os,
    prediction_engine,
    self_model,
    trend_engine,
    you_model,
)
from ..db import get_db
from ..schemas import DecideIn

router = APIRouter(prefix="/cognitive", tags=["cognitive"])


@router.get("/patterns")
def get_patterns(db: Session = Depends(get_db)):
    """Discovered behavioural correlations (contemporaneous + time-lagged)."""
    return pattern_engine.discover(db)


@router.get("/model")
def get_model(db: Session = Depends(get_db)):
    """The digital twin: evidence-backed traits + knowledge distribution."""
    return cognitive_model.build(db)


@router.get("/predictions")
def get_predictions(db: Session = Depends(get_db)):
    """Probabilistic forecasts (burnout, completion, decay, habit stability)."""
    return prediction_engine.forecast(db)


@router.get("/trends")
def get_trends(window_days: int = 30, db: Session = Depends(get_db)):
    """How the person is changing: rising / fading / emerging / dormant interests."""
    return trend_engine.build(db, window_days=window_days)


@router.get("/simulate")
def get_simulation(db: Session = Depends(get_db)):
    """Life Simulation: plausible 30d/90d/1y/5y trajectories + counterfactuals."""
    return life_sim.simulate(db)


@router.get("/chapters")
def get_chapters(db: Session = Depends(get_db)):
    """Life chapters auto-detected from sustained shifts in dominant focus."""
    return chapters.detect(db)


@router.get("/identity")
def get_identity(window_days: int = 90, db: Session = Depends(get_db)):
    """Identity alignment: stated goals vs. observed behaviour (claim vs. pursuit)."""
    return identity.assess(db, window_days=window_days)


@router.get("/habits")
def get_habits(weeks: int = 12, db: Session = Depends(get_db)):
    """Habit Genome: recurring behaviours as living entities (forming→dead) + outcomes."""
    return habit_genome.build(db, weeks=weeks)


@router.get("/decisions")
def get_decisions(db: Session = Depends(get_db)):
    """Decision Genome: inferred decisions, their outcomes, and follow-through patterns."""
    return decision_genome.build(db)


@router.get("/blind-spots")
def get_blind_spots(db: Session = Depends(get_db)):
    """Blind spots: hidden structures synthesised across the cognitive engines."""
    return blind_spots.build(db)


@router.get("/os")
def get_personal_os(db: Session = Depends(get_db)):
    """Personal OS: current → desired → distance → obstacles → leverage points."""
    return personal_os.build(db)


@router.get("/knowledge-graph")
def get_knowledge_graph(db: Session = Depends(get_db)):
    """Knowledge Evolution Graph: how concepts emerged and fed into one another."""
    return knowledge_graph.build(db)


@router.get("/learning")
def get_learning(window_days: int = 30, db: Session = Depends(get_db)):
    """Learning model: per-concept knowledge, retention/decay, and learning status."""
    return learning_model.build(db, recent_window_days=window_days)


@router.get("/self-model")
def get_self_model(db: Session = Depends(get_db)):
    """Self-Model: what you say about yourself, reconciled against what your behaviour shows."""
    return self_model.build(db)


@router.get("/you-model")
def get_you_model(db: Session = Depends(get_db)):
    """The You-Model: what you value, learned from your own behaviour (priors + revealed preference)."""
    return you_model.build(db)


@router.post("/decide")
def post_decide(payload: DecideIn, db: Session = Depends(get_db)):
    """Weigh options the way you would, using your learned value profile."""
    weights = you_model.build(db).get("weights", {})
    options = [{"name": o.name, **o.features} for o in payload.options]
    result = you_model.decide(options, weights)
    result["weights"] = weights
    return result
