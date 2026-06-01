"""Daily feature engineering for the active-day predictor.

Builds a continuous day-by-day timeline over the user's whole history and, for
each day, engineers features computed ONLY from prior days (no leakage). The
label is whether that day had any activity.
"""

from __future__ import annotations

from datetime import date, timedelta

# NOTE: no absolute time index — it leaks under a time-based split (the test
# window holds values never seen in training) and doesn't generalise to the
# future. Everything here is a relative/recent-history signal.
FEATURE_NAMES = [
    "mon", "tue", "wed", "thu", "fri", "sat", "sun",
    "is_weekend",
    "days_since_active",   # capped
    "active_prev_1",
    "active_prev_3",
    "active_prev_7",
    "active_prev_14",
    "commits_prev_7",
    "streak",              # consecutive active days ending yesterday
]


def daily_counts(mems: list[dict]) -> tuple[dict[date, int], date, date]:
    counts: dict[date, int] = {}
    for m in mems:
        d = m["ts"].date()
        counts[d] = counts.get(d, 0) + 1
    start, end = min(counts), max(counts)
    return counts, start, end


def _features_for(day: date, idx: int, span: int, counts: dict[date, int]) -> list[float]:
    dow = day.weekday()  # Mon=0 … Sun=6
    onehot = [1.0 if dow == k else 0.0 for k in range(7)]

    def active(d: date) -> int:
        return 1 if counts.get(d, 0) > 0 else 0

    # days since last active day (capped at 30)
    dsa = 0
    probe = day - timedelta(days=1)
    while dsa < 30 and counts.get(probe, 0) == 0:
        dsa += 1
        probe -= timedelta(days=1)

    prev1 = active(day - timedelta(days=1))
    prev3 = sum(active(day - timedelta(days=k)) for k in range(1, 4))
    prev7 = sum(active(day - timedelta(days=k)) for k in range(1, 8))
    prev14 = sum(active(day - timedelta(days=k)) for k in range(1, 15))
    commits7 = sum(counts.get(day - timedelta(days=k), 0) for k in range(1, 8))

    streak = 0
    probe = day - timedelta(days=1)
    while counts.get(probe, 0) > 0:
        streak += 1
        probe -= timedelta(days=1)

    return onehot + [
        1.0 if dow >= 5 else 0.0,
        float(dsa),
        float(prev1),
        float(prev3),
        float(prev7),
        float(prev14),
        float(commits7),
        float(streak),
    ]


def build_dataset(mems: list[dict]) -> tuple[list[list[float]], list[int], list[date]]:
    """X, y, dates over every day in the span. y=1 if the day had activity."""
    counts, start, end = daily_counts(mems)
    span = (end - start).days
    X: list[list[float]] = []
    y: list[int] = []
    dates: list[date] = []
    d = start
    idx = 0
    while d <= end:
        X.append(_features_for(d, idx, span, counts))
        y.append(1 if counts.get(d, 0) > 0 else 0)
        dates.append(d)
        d += timedelta(days=1)
        idx += 1
    return X, y, dates


def features_for_future(target: date, counts: dict[date, int], start: date, end: date) -> list[float]:
    """Feature vector for a date beyond the training window (e.g. tomorrow)."""
    span = (end - start).days
    idx = (target - start).days
    return _features_for(target, idx, span, counts)
