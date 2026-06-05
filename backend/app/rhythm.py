"""Time-of-day rhythm — the single shared definition.

Both the Cognitive Twin's ``attention_rhythm`` trait and the Pattern Engine's
``peak_window`` pattern used to compute "when are you active" independently — one
from the *unweighted modal hour*, the other from an *importance-weighted 4-hour
block* — so they could disagree and look contradictory ("Night owl" vs "peaks
10:00–14:00"). This module is the one source of truth they now both call:
the same importance-weighted 24-bucket histogram, the same best window, and a
label derived from that window's centre.

Pure and dependency-free — unit-testable without a database.
"""

from __future__ import annotations

HOURS = 24


def best_window(weight: list[float], length: int = 4) -> tuple[int, int, float]:
    """Best contiguous ``length``-hour window (wrapping midnight).

    Returns ``(start_hour, end_hour, share)`` where share is the fraction of
    total weight inside the window. With no weight, returns a zero-share window.
    """
    total = sum(weight)
    if total <= 0 or not weight:
        return (0, length % HOURS, 0.0)
    best_share, best_start = -1.0, 0
    for s in range(HOURS):
        share = sum(weight[(s + k) % HOURS] for k in range(length)) / total
        if share > best_share:
            best_share, best_start = share, s
    return (best_start, (best_start + length) % HOURS, round(best_share, 3))


def window_center(start: int, length: int = 4) -> int:
    """Centre hour of a window starting at ``start`` (wraps midnight)."""
    return (start + length // 2) % HOURS


def rhythm_label(hour: int) -> str:
    """Daypart label for an hour (UTC). Shared by every engine that names a rhythm."""
    if hour >= 21 or hour < 5:
        return "Night owl"
    if hour < 11:
        return "Early bird"
    if hour < 17:
        return "Afternoon"
    return "Evening"
