"""Fractal Memory (Memory-Architecture V3).

Life forms a hierarchy — Life → Era → Year → Event → memory — and each level
summarises the one beneath it, so a user can zoom out to decades or in to a single
day. This module rolls clustered events up into that hierarchy and lets a caller
ask for any zoom level.

The pure core (`build_fractal` + `zoom`) works on leaf events and is
unit-testable; `build(db)` derives the leaves by clustering the Memory store
through the events module.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone

LEVELS = ("life", "era", "year", "event")


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class LeafEvent:
    date: datetime
    title: str
    theme: str = "general"
    importance: float = 0.5


@dataclass
class FractalNode:
    level: str
    label: str
    start: datetime
    end: datetime
    size: int                          # leaf events beneath this node
    importance: float                  # peak importance in the subtree
    dominant_theme: str
    top_title: str                     # highest-importance descendant
    children: list["FractalNode"] = field(default_factory=list)

    def as_dict(self, depth: int = -1) -> dict:
        d = {
            "level": self.level,
            "label": self.label,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "size": self.size,
            "importance": round(self.importance, 3),
            "dominant_theme": self.dominant_theme,
            "top_title": self.top_title,
        }
        if depth != 0:
            d["children"] = [c.as_dict(depth - 1) for c in self.children]
        return d


def _summarize(level: str, label: str, leaves: list[LeafEvent],
               children: list[FractalNode]) -> FractalNode:
    start = min(l.date for l in leaves)
    end = max(l.date for l in leaves)
    themes: Counter[str] = Counter()
    for l in leaves:
        themes[l.theme] += l.importance
    dominant = themes.most_common(1)[0][0] if themes else "general"
    top = max(leaves, key=lambda l: l.importance)
    return FractalNode(
        level=level, label=label, start=start, end=end,
        size=len(leaves), importance=top.importance,
        dominant_theme=dominant, top_title=top.title, children=children,
    )


def build_fractal(events: list[LeafEvent], era_years: int = 5) -> FractalNode | None:
    """Roll leaf events up into Life → Era → Year → Event."""
    if not events:
        return None
    leaves = sorted(events, key=lambda e: e.date)

    # Year level.
    by_year: dict[int, list[LeafEvent]] = {}
    for e in leaves:
        by_year.setdefault(e.date.year, []).append(e)
    year_nodes: dict[int, FractalNode] = {}
    for yr, evs in sorted(by_year.items()):
        children = [
            FractalNode("event", e.title, e.date, e.date, 1, e.importance, e.theme, e.title)
            for e in sorted(evs, key=lambda x: x.date)
        ]
        year_nodes[yr] = _summarize("year", str(yr), evs, children)

    # Era level (fixed multi-year buckets).
    by_era: dict[int, list[int]] = {}
    for yr in year_nodes:
        by_era.setdefault(yr // era_years, []).append(yr)
    era_nodes: list[FractalNode] = []
    for era_key, yrs in sorted(by_era.items()):
        yrs.sort()
        era_leaves = [e for yr in yrs for e in by_year[yr]]
        label = f"{yrs[0]}–{yrs[-1]}" if yrs[0] != yrs[-1] else str(yrs[0])
        era_nodes.append(_summarize("era", label, era_leaves,
                                    [year_nodes[yr] for yr in yrs]))

    return _summarize("life", "Life", leaves, era_nodes)


def zoom(root: FractalNode | None, level: str) -> list[dict]:
    """Flatten the tree to a single zoom level (life | era | year | event)."""
    if root is None:
        return []
    out: list[dict] = []

    def walk(node: FractalNode):
        if node.level == level:
            out.append(node.as_dict(depth=0))
            return
        for c in node.children:
            walk(c)

    walk(root)
    return out


# --- DB adapter -------------------------------------------------------------
def build(db, era_years: int = 5) -> dict:
    from . import events as events_mod

    # Reuse event clustering, then theme each event by its dominant person/entity.
    res = events_mod.build(db)
    leaves: list[LeafEvent] = []
    for ev in res.get("events", []):
        people = ev.get("people") or []
        theme = people[0] if people else "general"
        leaves.append(LeafEvent(
            date=datetime.fromisoformat(ev["start"]),
            title=ev["title"],
            theme=theme,
            importance=ev.get("importance", 0.5),
        ))

    root = build_fractal(leaves, era_years=era_years)
    return {
        "generated_at": _now().isoformat(),
        "ready": root is not None,
        "events": len(leaves),
        "tree": root.as_dict() if root else None,
        "by_level": {lvl: zoom(root, lvl) for lvl in ("era", "year")},
    }
