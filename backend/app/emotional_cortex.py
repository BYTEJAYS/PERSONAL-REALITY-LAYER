"""Emotional Cortex (Ledger).

Turns the emotional colouring of memories into understanding: the overall
valence of a life, the mix of feelings, how mood moves month to month, and
whether stress is rising lately. Pure ``analyze`` is DB-free and unit-testable;
``build(db)`` reads the ``emotion`` tag carried on memories.

Describes, never diagnoses. No emotional data → ``ready: false`` (no fabrication).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# Coarse valence per emotion label (-1 negative .. +1 positive). Unknown → 0 (neutral).
EMOTION_VALENCE = {
    "joy": 1.0, "happy": 0.9, "excitement": 0.9, "excited": 0.9, "love": 0.9,
    "grateful": 0.8, "proud": 0.8, "content": 0.6, "calm": 0.5, "hopeful": 0.6,
    "neutral": 0.0, "surprise": 0.1,
    "tired": -0.3, "bored": -0.3, "confused": -0.3,
    "stress": -0.7, "stressed": -0.7, "anxious": -0.7, "anxiety": -0.7, "fear": -0.8,
    "sad": -0.8, "sadness": -0.8, "angry": -0.8, "anger": -0.8,
    "frustrated": -0.6, "frustration": -0.6, "lonely": -0.7, "grief": -0.9,
}
STRESS_EMOTIONS = {
    "stress", "stressed", "anxious", "anxiety", "fear", "sad", "sadness", "angry",
    "anger", "frustrated", "frustration", "lonely", "grief",
}
STRESS_WINDOW_DAYS = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


def valence(emotion: str) -> float:
    return EMOTION_VALENCE.get((emotion or "").strip().lower(), 0.0)


@dataclass
class EmotionEvent:
    date: datetime
    emotion: str
    importance: float = 0.5


def _month(d: datetime) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def analyze(events: list[EmotionEvent], today: datetime | None = None) -> dict:
    today = today or _now()
    tagged = [e for e in events if e.emotion]
    if not tagged:
        return {"ready": False, "message": "No emotional signal recorded yet."}

    counts = Counter(e.emotion.strip().lower() for e in tagged)
    # Importance-weighted overall valence.
    wsum = sum(e.importance for e in tagged) or 1.0
    overall = sum(valence(e.emotion) * e.importance for e in tagged) / wsum
    mood = ("positive" if overall > 0.15 else "negative" if overall < -0.15 else "balanced")

    # Monthly mood series: dominant emotion + average valence.
    by_month: dict[str, list[EmotionEvent]] = {}
    for e in tagged:
        by_month.setdefault(_month(e.date), []).append(e)
    timeline = []
    for m in sorted(by_month):
        evs = by_month[m]
        dom = Counter(e.emotion.strip().lower() for e in evs).most_common(1)[0][0]
        avg_v = sum(valence(e.emotion) for e in evs) / len(evs)
        timeline.append({"month": m, "dominant": dom, "valence": round(avg_v, 3),
                         "count": len(evs)})

    # Stress: baseline share vs the recent window — is stress rising lately?
    stress_total = sum(1 for e in tagged if e.emotion.strip().lower() in STRESS_EMOTIONS)
    baseline_share = stress_total / len(tagged)
    cutoff = today - timedelta(days=STRESS_WINDOW_DAYS)
    recent = [e for e in tagged if e.date >= cutoff]
    recent_share = (
        sum(1 for e in recent if e.emotion.strip().lower() in STRESS_EMOTIONS) / len(recent)
        if recent else 0.0
    )
    rising = bool(recent) and recent_share > baseline_share + 0.15
    stress = {
        "baseline_share": round(baseline_share, 3),
        "recent_share": round(recent_share, 3),
        "recent_window_days": STRESS_WINDOW_DAYS,
        "rising": rising,
    }

    top = [{"emotion": e, "count": n, "share": round(n / len(tagged), 3)}
           for e, n in counts.most_common(8)]
    parts = [f"{len(tagged)} emotional memories", f"overall mood {mood}"]
    if rising:
        parts.append("stress trending up recently")
    return {
        "ready": True,
        "generated_at": today.isoformat(),
        "overall_valence": round(overall, 3),
        "mood": mood,
        "emotions": top,
        "mood_timeline": timeline,
        "stress": stress,
        "explanation": "; ".join(parts) + ".",
    }


# --- DB adapter -------------------------------------------------------------
def build(db) -> dict:
    from sqlalchemy import select
    from .models import Memory

    rows = db.execute(
        select(Memory.ts, Memory.emotion, Memory.importance).where(Memory.emotion.isnot(None))
    ).all()
    events = []
    for ts, emotion, imp in rows:
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        events.append(EmotionEvent(ts, emotion, imp if imp is not None else 0.5))
    return analyze(events)
