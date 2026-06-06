"""Wisdom Engine — distilled life lessons from your own history.

The cognitive twin already mines patterns (decisions, habits, values, blind
spots). This engine is the *synthesis layer above them*: it turns those raw
patterns into plain, second-person **wisdom** — the kind of line you'd want a
future self to remember:

    "Your best work comes from going deep on one thing."
    "Things you start during busy stretches tend to get abandoned."
    "Weeks you keep up the gym track with your most productive weeks."

Each insight is one of five kinds:

    success_pattern — a condition that reliably goes well for you
    pitfall         — a condition that reliably goes badly for you
    growth_driver   — a habit that lifts your good periods
    lesson          — a recurring hard spot worth a deliberate plan
    philosophy      — what you fundamentally seem to value

Every line traces to evidence and carries a confidence — nothing is invented.
The pure functions take already-computed engine outputs (DB-free, unit-testable);
``build(db)`` runs the source engines and feeds them in. This mirrors the
``blind_spots`` / ``personal_os`` synthesis pattern.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class WisdomInsight:
    category: str          # success_pattern | pitfall | growth_driver | lesson | philosophy
    statement: str         # the wisdom, second person
    confidence: float      # 0..1
    strength: float        # 0..1 how strong the underlying signal is
    sources: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    # Stable identity (so the Principle Engine can reinforce the same insight across
    # runs) + how many real data points back it.
    key: str = ""
    evidence_count: int = 1
    exceptions: list[str] = field(default_factory=list)


# --- pure detectors ---------------------------------------------------------
def from_decision_patterns(decisions: dict) -> list[WisdomInsight]:
    """Turn decision-genome follow-through patterns into success/pitfall wisdom."""
    out: list[WisdomInsight] = []
    for p in (decisions or {}).get("patterns", []):
        lift = p.get("lift", 0.0)
        if abs(lift) < 0.15:
            continue
        name = p.get("name")
        conf = p.get("confidence", 0.5)
        obs = p.get("observation", "")
        positive = lift > 0
        if name == "collaborative":
            stmt = ("You follow through more when you bring other people in — "
                    "make the things that matter shared, not solo."
                    if positive else
                    "You finish more when you work solo — collaborations tend to "
                    "fizzle for you, so guard your core work from depending on others.")
        elif name == "busy_start":
            stmt = ("Things you start even in busy stretches tend to stick — "
                    "pressure doesn't break your follow-through."
                    if positive else
                    "Things you start during busy stretches tend to get abandoned — "
                    "protect new commitments from your most crowded weeks.")
        else:
            stmt = obs or f"A repeatable pattern in how you follow through ({name})."
        out.append(WisdomInsight(
            category="success_pattern" if positive else "pitfall",
            statement=stmt,
            confidence=round(conf, 3),
            strength=round(min(1.0, abs(lift)), 3),
            sources=["decision_genome"],
            evidence=[obs] if obs else [],
            key=f"decision:{name}:{'pos' if positive else 'neg'}",
            evidence_count=int(p.get("sample", 1)),
        ))
    return out


def from_habits(habits: dict) -> list[WisdomInsight]:
    """A habit that correlates with productive weeks is a growth driver; if it has
    faded, it becomes a lesson to revive it."""
    out: list[WisdomInsight] = []
    base_conf = (habits or {}).get("confidence", 0.5)
    for h in (habits or {}).get("habits", []):
        corr = h.get("outcome_correlation", 0.0)
        if corr < 0.35:
            continue
        name = h.get("name", "this")
        stage = h.get("stage", "")
        cons = h.get("consistency", 0.0)
        ec = int(sum((h.get("evidence") or {}).get("weekly", []))) or 1
        if stage in ("declining", "dormant", "dead"):
            out.append(WisdomInsight(
                category="lesson",
                statement=f"{name} used to track with your best weeks, but you've let "
                          f"it fade — reviving it is high-leverage.",
                confidence=round(base_conf, 3),
                strength=round(min(1.0, corr), 3),
                sources=["habit_genome"],
                evidence=[f"outcome correlation {corr}", f"stage: {stage}"],
                key=f"habit:{name}", evidence_count=ec,
            ))
        else:
            out.append(WisdomInsight(
                category="growth_driver",
                statement=f"Weeks you keep up {name} tend to be your most productive — "
                          f"it's a hidden engine for you, so protect it.",
                confidence=round(base_conf, 3),
                strength=round(min(1.0, corr), 3),
                sources=["habit_genome"],
                evidence=[f"outcome correlation {corr}", f"consistency {cons}"],
                key=f"habit:{name}", evidence_count=ec,
            ))
    return out


def from_values(you_model: dict) -> list[WisdomInsight]:
    """The you-model's value profile → a single grounding philosophy."""
    profile = (you_model or {}).get("value_profile", [])
    if not profile:
        return []
    conf = (you_model or {}).get("confidence", 0.5)
    pairs = int((you_model or {}).get("data_basis", {}).get("comparison_pairs", 0))
    joined = ", ".join(profile[:3])
    return [WisdomInsight(
        category="philosophy",
        statement=f"At your core you value {joined}. Your strongest work honors these; "
                  f"the choices you regret usually betray them.",
        confidence=round(conf, 3),
        strength=round(min(1.0, 0.5 + conf / 2), 3),
        sources=["you_model"],
        evidence=list(profile[:4]),
        key="values", evidence_count=pairs or len(profile),
    )]


def from_blind_spots(blind: dict) -> list[WisdomInsight]:
    """Claim-vs-pursuit misalignments become lessons (the actionable, self-honest
    kind). Other blind-spot categories are already covered by the pattern/habit
    detectors above, so we don't duplicate them here."""
    out: list[WisdomInsight] = []
    for s in (blind or {}).get("blind_spots", []):
        if s.get("category") != "misalignment":
            continue
        finding = s.get("finding") or s.get("title", "")
        slug = (s.get("title", "") or "gap").lower().replace(" ", "_")[:40]
        out.append(WisdomInsight(
            category="lesson",
            statement=f"{finding} — a gap between what you say matters and where your "
                      f"time goes. Closing it is worth a deliberate plan.",
            confidence=round(s.get("confidence", 0.5), 3),
            strength=round(s.get("severity", 0.5), 3),
            sources=["identity"],
            evidence=[finding] if finding else [],
            key=f"misalign:{slug}", evidence_count=1,
        ))
    return out


def from_struggles(struggles: list[dict]) -> list[WisdomInsight]:
    """Recurring hard spots from the journal (a life-domain that keeps showing up
    with negative emotion). Each item: {theme, count, total}."""
    out: list[WisdomInsight] = []
    for s in struggles or []:
        count = s.get("count", 0)
        total = max(1, s.get("total", 0))
        if count < 3:
            continue
        theme = s.get("theme", "this area")
        share = count / total
        out.append(WisdomInsight(
            category="lesson",
            statement=f"{theme} is a recurring hard spot — it's come up {count} times. "
                      f"It tends to need a plan, not just willpower.",
            confidence=round(min(0.9, 0.4 + count / 20), 3),
            strength=round(min(1.0, share + 0.2), 3),
            sources=["journal"],
            evidence=[f"{count} of {total} entries"],
            key=f"struggle:{theme}", evidence_count=count,
        ))
    return out


def synthesize(
    decisions: dict | None = None,
    habits: dict | None = None,
    you_model: dict | None = None,
    blind: dict | None = None,
    struggles: list[dict] | None = None,
) -> dict:
    """Merge every detector into one ranked, de-duplicated body of wisdom."""
    insights: list[WisdomInsight] = []
    insights += from_decision_patterns(decisions or {})
    insights += from_habits(habits or {})
    insights += from_values(you_model or {})
    insights += from_blind_spots(blind or {})
    insights += from_struggles(struggles or [])

    # De-dup on the statement, keeping the strongest copy.
    best: dict[str, WisdomInsight] = {}
    for ins in insights:
        key = ins.statement.strip().lower()
        cur = best.get(key)
        if cur is None or (ins.strength * ins.confidence) > (cur.strength * cur.confidence):
            best[key] = ins
    ranked = sorted(best.values(), key=lambda i: i.strength * i.confidence, reverse=True)

    by_cat: dict[str, int] = {}
    for i in ranked:
        by_cat[i.category] = by_cat.get(i.category, 0) + 1

    return {
        "generated_at": _now().isoformat(),
        "ready": bool(ranked),
        "note": "Lessons distilled from your own history. Descriptive and evidence-tied, "
                "never invented — and it sharpens as you record more.",
        "category_counts": by_cat,
        "wisdom": [asdict(i) for i in ranked[:20]],
    }


# --- DB adapter -------------------------------------------------------------
def _recurring_struggles(db) -> list[dict]:
    """Tally journal life-domains that recur with negative emotion."""
    try:
        from sqlalchemy import select

        from .emotional_cortex import valence
        from .models import Memory

        rows = db.execute(
            select(Memory).where(Memory.source == "journal")
        ).scalars().all()
        counts: dict[str, int] = {}
        total = 0
        for m in rows:
            total += 1
            seen: set[str] = set()
            for ev in ((m.meta or {}).get("journal", {}) or {}).get("events", []):
                cat, emo = ev.get("category"), ev.get("emotion")
                if cat and cat != "Life" and emo and valence(emo) <= -0.3 and cat not in seen:
                    counts[cat] = counts.get(cat, 0) + 1
                    seen.add(cat)
        return [{"theme": k, "count": v, "total": total}
                for k, v in sorted(counts.items(), key=lambda kv: -kv[1])]
    except Exception:
        return []


def build(db) -> dict:
    """Run the source engines (each defensively) and synthesise wisdom."""
    from . import blind_spots, decision_genome, habit_genome, you_model

    def safe(fn):
        try:
            return fn(db) or {}
        except Exception:
            return {}

    return synthesize(
        decisions=safe(decision_genome.build),
        habits=safe(habit_genome.build),
        you_model=safe(you_model.build),
        blind=safe(blind_spots.build),
        struggles=_recurring_struggles(db),
    )
