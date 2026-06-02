"""Self-Model — what you SAY about yourself, reconciled against what you DO.

The cognitive twin (``cognitive_model``) is built from behaviour: it only sees
the projects that survived into git. Reflective text is the other half — it's
where you describe the patterns the data can't see (the abandoned work, the
emotional reality, the fears). This module turns that text into structured
*self-claims* and then sets them against the behavioural traits, so the brain
can hold both and, crucially, **flag where your self-view and your behaviour
disagree** instead of flattering whichever side it happened to read.

Design choices:
- Deterministic, dependency-free extraction (phrase taxonomy), so it works
  today without a language model and is unit-testable. An LLM can refine the
  extraction later; the reconciliation logic stays the same.
- It never overwrites the evidence-based twin. Self-report and behaviour are
  kept as distinct views; the output is their agreement/divergence.

Pure cores are DB-free; ``build(db)`` is the adapter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

# Each dimension is something a person can both *claim* and *behave*. polarity
# convention: +1 = the "disciplined / strong" pole, -1 = the "struggling" pole.
# `behavioral_axis` links to how the trait shows up in behaviour for reconciling
# (None = self-report only, no behavioural counterpart).
@dataclass
class Dimension:
    name: str
    pos_desc: str           # what +polarity means in words
    neg_desc: str           # what -polarity means in words
    pos_patterns: list[str]
    neg_patterns: list[str]
    behavioral_axis: str | None = None  # "persistence" | "focus" | "curiosity" | "followthrough"


DIMENSIONS: list[Dimension] = [
    Dimension(
        "consistency",
        "shows up consistently, daily", "works in bursts, can't sustain a rhythm",
        [r"consistent", r"show up daily", r"every ?day", r"discipline", r"routine", r"steady"],
        [r"burst", r"inconsistent", r"can'?t (show up|sustain)", r"don'?t sustain",
         r"drop off", r"lose (rhythm|momentum)", r"intensity", r"day 1.*day"],
        behavioral_axis="persistence",
    ),
    Dimension(
        "follow_through",
        "finishes and ships what they start", "abandons / restarts, rarely finishes",
        [r"finish", r"ship", r"complete", r"see (it|things) through", r"follow through"],
        [r"abandon", r"restart", r"start (things|strong).*(not|don'?t) (stay|finish)",
         r"jump between", r"never (built|finished|shipped)", r"don'?t finish", r"unfinished"],
        behavioral_axis="followthrough",
    ),
    Dimension(
        "execution_vs_planning",
        "biases to building/doing", "hides in planning/analysis instead of executing",
        [r"\bbuild\b", r"\bexecut", r"\bdo(ing)? the work\b", r"\bship\b", r"hands.?on"],
        [r"over.?think", r"over.?plan", r"plan(ning)? (a lot|systems)", r"analy[sz]e instead",
         r"thinking feels productive", r"avoid(ance|ing)? (of )?(hard|boring) (work|execution)"],
        behavioral_axis=None,
    ),
    Dimension(
        "emotional_regulation",
        "acts on a system regardless of mood", "emotionally reactive, mood/motivation-driven",
        [r"regardless of (mood|feeling)", r"operate on a system", r"disciplined regardless"],
        [r"emotionally reactive", r"mood", r"depends on (motivation|feeling|mood)",
         r"need to feel", r"motivation", r"validation", r"distract", r"operating on feelings"],
        behavioral_axis=None,
    ),
    Dimension(
        "focus",
        "holds deep focus", "easily distracted, loses focus",
        [r"deep focus", r"locked? in", r"deep work", r"undistracted"],
        [r"distract", r"lose (focus|rhythm)", r"easily (hit|pulled)", r"attention (affects|drifts)"],
        behavioral_axis="focus",
    ),
    Dimension(
        "novelty_chasing",
        "sticks with the familiar / commits to one thing", "chases new ideas, shiny things",
        [r"commit to one", r"stick (with|to)", r"stay on one"],
        [r"chase (every )?(shiny|new)", r"jump between ideas", r"new (plans|ideas)",
         r"shiny idea", r"chasing", r"new project"],
        behavioral_axis="curiosity",
    ),
    Dimension(
        "identity_security",
        "secure, earns it daily", "protects a 'high potential' identity, fears full commitment",
        [r"earn (everything|it) daily", r"i am becoming", r"secure"],
        [r"potential", r"identity", r"i'?m special", r"could be great", r"seen as (smart|deep|exceptional)",
         r"fear(s|ing)? (of )?fail", r"protect", r"fantasy"],
        behavioral_axis=None,
    ),
]

# How a behavioural signal maps onto the +1/-1 polarity of a dimension.
# value is a number in [0,1] (trait score or rate); we convert to [-1,1].
_SENTENCE = re.compile(r"[.;\n!?]+")


@dataclass
class SelfClaim:
    dimension: str
    polarity: float        # -1..1  (sign = which pole, magnitude = how strongly stated)
    strength: float        # 0..1 confidence from how much text supports it
    pole: str              # readable description of the claimed pole
    hits: int
    quote: str             # representative sentence from the text


@dataclass
class Divergence:
    dimension: str
    kind: str              # "divergence" | "alignment"
    self_view: str
    behavioral_view: str
    note: str
    self_polarity: float
    behavioral_polarity: float
    gap: float


def _scan(dim: Dimension, text: str) -> tuple[int, str, int, str]:
    """Per-sentence tally for one dimension. A sentence matching a negative
    pattern is counted negative only (never also positive) so a negated positive
    like "can't show up daily" can't cancel itself out."""
    pos_rx = [re.compile(p, re.IGNORECASE) for p in dim.pos_patterns]
    neg_rx = [re.compile(p, re.IGNORECASE) for p in dim.neg_patterns]
    pos_hits = neg_hits = 0
    pos_quote = neg_quote = ""
    for sentence in _SENTENCE.split(text):
        s = sentence.strip()
        if not s:
            continue
        if any(rx.search(s) for rx in neg_rx):
            neg_hits += 1
            neg_quote = neg_quote or s[:160]
        elif any(rx.search(s) for rx in pos_rx):
            pos_hits += 1
            pos_quote = pos_quote or s[:160]
    return pos_hits, pos_quote, neg_hits, neg_quote


def extract_claims(text: str) -> list[SelfClaim]:
    """Turn reflective text into structured self-claims across the taxonomy."""
    claims: list[SelfClaim] = []
    for dim in DIMENSIONS:
        pos_hits, pos_quote, neg_hits, neg_quote = _scan(dim, text)
        total = pos_hits + neg_hits
        if total == 0:
            continue
        polarity = round((pos_hits - neg_hits) / total, 3)
        strength = round(min(0.9, 0.3 + total / 8.0), 3)
        if polarity >= 0:
            pole, quote = dim.pos_desc, pos_quote or neg_quote
        else:
            pole, quote = dim.neg_desc, neg_quote or pos_quote
        claims.append(SelfClaim(dim.name, polarity, strength, pole, total, quote))
    claims.sort(key=lambda c: c.strength, reverse=True)
    return claims


def reconcile(claims: list[SelfClaim], behavioral: dict[str, float]) -> list[Divergence]:
    """Compare self-claims to behavioural polarities on shared axes.

    `behavioral` maps an axis name (persistence/focus/curiosity/followthrough)
    to a [-1,1] polarity (+1 = strong/disciplined pole). Only dimensions with a
    behavioural counterpart present can be reconciled.
    """
    by_axis = {d.name: d for d in DIMENSIONS}
    out: list[Divergence] = []
    for c in claims:
        dim = by_axis.get(c.dimension)
        if not dim or dim.behavioral_axis is None:
            continue
        if dim.behavioral_axis not in behavioral:
            continue
        bpol = behavioral[dim.behavioral_axis]
        gap = round(abs(c.polarity - bpol), 3)
        self_view = dim.pos_desc if c.polarity >= 0 else dim.neg_desc
        beh_view = dim.pos_desc if bpol >= 0 else dim.neg_desc
        if c.polarity * bpol < 0 and gap >= 0.6:
            note = (
                f"You describe yourself as someone who {dim.neg_desc if c.polarity < 0 else dim.pos_desc}, "
                f"but your behaviour reads as {beh_view}."
            )
            # Survivorship caveat where the data is git-biased.
            if dim.behavioral_axis in ("followthrough", "persistence") and bpol > 0:
                note += (" The data only sees the projects that survived into commits — "
                         "it can't see the ones you abandoned before they left a trace.")
            out.append(Divergence(c.dimension, "divergence", self_view, beh_view, note,
                                   c.polarity, bpol, gap))
        else:
            out.append(Divergence(
                c.dimension, "alignment", self_view, beh_view,
                f"Your self-view ({self_view}) and your behaviour agree here.",
                c.polarity, bpol, gap))
    # Divergences first, then by size of gap.
    out.sort(key=lambda d: (d.kind != "divergence", -d.gap))
    return out


# --- DB adapter -------------------------------------------------------------
_REFLECTIVE_SOURCES = ("self-analysis", "note", "journal", "reflection", "diary")


def _behavioral_polarities(db) -> dict[str, float]:
    """Pull behavioural traits + follow-through into [-1,1] polarities."""
    from . import cognitive_model, decision_genome

    pol: dict[str, float] = {}
    try:
        twin = cognitive_model.build(db)
        for t in twin.get("traits") or []:
            name = (t.get("name") or "").lower()
            score = float(t.get("score", 0.5))
            p = round((score - 0.5) * 2, 3)
            if "persistence" in name:
                pol["persistence"] = p
            elif "focus" in name:
                pol["focus"] = p
            elif "curiosity" in name:
                # high curiosity ⇒ behaviourally novelty-seeking ⇒ -polarity on
                # the novelty_chasing axis (whose +pole is "sticks with one thing")
                pol["curiosity"] = round(-p, 3)
    except Exception:
        pass
    try:
        dg = decision_genome.build(db)
        if dg.get("ready") and "followthrough_rate" in dg:
            pol["followthrough"] = round((dg["followthrough_rate"] - 0.5) * 2, 3)
    except Exception:
        pass
    return pol


def build(db) -> dict:
    from sqlalchemy import select
    from .models import Memory

    now = datetime.now(timezone.utc).isoformat()
    rows = db.execute(
        select(Memory.content).where(Memory.source.in_(_REFLECTIVE_SOURCES))
    ).scalars().all()
    text = "\n".join(c for c in rows if c)

    if not text.strip():
        return {"generated_at": now, "ready": False,
                "message": "No reflective text yet. Paste some writing about yourself to build this."}

    claims = extract_claims(text)
    behavioral = _behavioral_polarities(db)
    findings = reconcile(claims, behavioral)
    divergences = [f for f in findings if f.kind == "divergence"]

    return {
        "generated_at": now,
        "ready": bool(claims),
        "note": ("What you say about yourself, set against what your behaviour shows. "
                 "Divergences are where your self-view and your data disagree."),
        "reflective_memories": len(rows),
        "self_claims": [c.__dict__ for c in claims],
        "reconciliation": [f.__dict__ for f in findings],
        "divergence_count": len(divergences),
        "summary": _summary(claims, divergences),
    }


def _summary(claims: list[SelfClaim], divergences: list[Divergence]) -> str:
    if not claims:
        return "No self-claims extracted yet."
    top = claims[0]
    parts = [f"You describe yourself most strongly as someone who {top.pole}."]
    if divergences:
        d = divergences[0]
        parts.append(f"Biggest tension with your behaviour: {d.note}")
    else:
        parts.append("So far your self-view and your behavioural data broadly agree.")
    return " ".join(parts)


def persona_section(db) -> str:
    """A compact block for the persona prompt: self-view + tensions with behaviour."""
    try:
        sm = build(db)
    except Exception:
        return ""
    if not sm.get("ready"):
        return ""
    lines = []
    claims = sm.get("self_claims") or []
    if claims:
        lines.append("How they describe themselves (their own words):")
        for c in claims[:5]:
            lines.append(f"- {c['pole']}")
    divs = [f for f in sm.get("reconciliation", []) if f["kind"] == "divergence"]
    if divs:
        lines.append("\nTensions between their self-view and their behaviour (call these out honestly when relevant):")
        for d in divs[:3]:
            lines.append(f"- {d['note']}")
    return "\n".join(lines)
