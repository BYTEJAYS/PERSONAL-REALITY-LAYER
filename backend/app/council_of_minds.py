"""Council of Minds — ten *genuinely different* reasoning lenses on a question.

The point of a council isn't ten voices that share your worldview — it's cognitive
diversity. These minds share your *facts* (your recorded principles), but each one
brings a different *prior*: what it optimises for, what it fears, what it
over-weights. So they can disagree — with each other, and with you. The Critic
argues the downside of a plan your own principles endorse; the Entrepreneur pushes
the bold move you'd hesitate on; the Scientist distrusts a belief you hold on thin
evidence. The value is precisely in that friction.

Each mind takes a **stance** (for / against / caution / depends / reframe) driven
by its bias, plus a one-line argument grounded in the principle most relevant to
its lens. The council then surfaces the **conflict**: how it splits, and the
single sharpest objection to weigh. Deterministic core (works with Jerry asleep);
an optional LLM call fuses a decisive verdict that honours the disagreement.

Pure ``deliberate`` is DB-free and unit-tested; ``build(db, question)`` convenes it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conviction(p: dict) -> float:
    return float(p.get("confidence", 0.0)) * math.log2(2 + int(p.get("evidence_count", 1)))


# stance vocabulary
FOR, AGAINST, CAUTION, DEPENDS, REFRAME = "for", "against", "caution", "depends", "reframe"
_OPPOSE = {AGAINST, CAUTION}


# Each arguer receives the principle(s) picked for its lens and a context dict
# {value_profile, commandments}; it returns (stance, take, drew_keys).
def _scientist(picked, ctx):
    if picked and int(picked[0].get("evidence_count", 0)) >= 5:
        return FOR, f"The data backs it — {picked[0]['statement']} Decide by evidence, then keep measuring.", [picked[0]["key"]]
    if picked:
        return CAUTION, f"You half-believe this — {picked[0]['statement']} — but the evidence is still thin. Don't bet big on it yet.", [picked[0]["key"]]
    return CAUTION, "You're running on gut here, not data. Get one real data point before you commit.", []


def _critic(picked, ctx):
    if picked:
        return AGAINST, f"Here's the trap: {picked[0]['statement']} Assume the rosy case is wrong and plan for that.", [picked[0]["key"]]
    return CAUTION, "What's the failure mode you're not naming? If you can't see one, you haven't looked hard enough.", []


def _optimist(picked, ctx):
    if picked:
        return FOR, f"Lean in — {picked[0]['statement']} The upside here is real; don't talk yourself out of it.", [picked[0]["key"]]
    return FOR, "What would make this clearly worth it — and what's the smallest step toward that?", []


def _strategist(picked, ctx):
    if picked:
        return FOR, f"In the long arc this compounds — {picked[0]['statement']} Choose the better decade, not the better week.", [picked[0]["key"]]
    return CAUTION, "Zoom out to ten years. If it doesn't matter then, don't let it dominate now.", []


def _philosopher(picked, ctx):
    vp = ctx.get("value_profile") or []
    if vp:
        return DEPENDS, f"It comes down to whether this honours what you value — {', '.join(vp[:3])}. If it does, do it; if not, no upside is worth it.", []
    return DEPENDS, "Does this fit who you're trying to become? Values first; tactics second.", []


def _psychologist(picked, ctx):
    if picked:
        return CAUTION, f"Mind the pattern: {picked[0]['statement']} How you'll feel in a week matters more than the urge right now.", [picked[0]["key"]]
    return FOR, "Check the feeling under the question. If it's fear talking, that's usually a reason to go, not stop.", []


def _historian(picked, ctx):
    if picked:
        return FOR, f"You've walked this before — {picked[0]['statement']} The track record is your best guide.", [picked[0]["key"]]
    return CAUTION, "When did you last face this, and how did it actually turn out? Don't repeat a forgotten mistake.", []


def _entrepreneur(picked, ctx):
    if picked:
        return FOR, f"Bias to action — {picked[0]['statement']} The downside is capped; the upside isn't. Move.", [picked[0]["key"]]
    return FOR, "Where's the asymmetric bet — small cost, large possible payoff? Take it before you're ready.", []


def _engineer(picked, ctx):
    if picked:
        return CAUTION, f"Don't make it a willpower bet — {picked[0]['statement']} Build the system first, then decide.", [picked[0]["key"]]
    return CAUTION, "What's the simplest reliable setup so this doesn't depend on you being disciplined?", []


def _creative(picked, ctx):
    return REFRAME, "Reject the binary. What's the third option nobody's naming — maybe combining two things you already do well?"  , []


@dataclass
class Mind:
    name: str
    lens: str
    bias: str
    prefers: tuple[str, ...]
    arguer: Callable


MINDS: list[Mind] = [
    Mind("Scientist", "Demands evidence", "evidence-first", ("growth_driver", "success_pattern"), _scientist),
    Mind("Critic", "Hunts the downside", "risk-averse", ("pitfall", "lesson"), _critic),
    Mind("Optimist", "Sees the upside", "upside-seeking", ("success_pattern", "growth_driver"), _optimist),
    Mind("Strategist", "Plays the long game", "long-term", ("philosophy",), _strategist),
    Mind("Philosopher", "Tests it against your values", "values-first", ("philosophy",), _philosopher),
    Mind("Psychologist", "Reads your patterns", "pattern-aware", ("lesson",), _psychologist),
    Mind("Historian", "Trusts the track record", "precedent-led", ("success_pattern", "growth_driver", "lesson"), _historian),
    Mind("Entrepreneur", "Bets on asymmetric upside", "action-first", ("growth_driver", "success_pattern"), _entrepreneur),
    Mind("Engineer", "Builds a reliable system", "systems-first", ("lesson", "growth_driver"), _engineer),
    Mind("Creative Thinker", "Finds the third option", "lateral", (), _creative),
]


def _pick(principles: list[dict], cats: tuple[str, ...], used: set[str], n: int = 1) -> list[dict]:
    def pool(exclude_used: bool):
        return [p for p in principles
                if p.get("category") in cats and p.get("status") in ("active", "forming")
                and (not exclude_used or p.get("key") not in used)]
    chosen = pool(True) or pool(False)
    chosen.sort(key=_conviction, reverse=True)
    return chosen[:n]


def deliberate(question: str, principles: list[dict], value_profile: list[str],
               commandments: list[dict], minds: list[Mind] | None = None) -> dict:
    """Each mind argues from its own bias; then surface the conflict + a verdict."""
    panel = minds if minds is not None else MINDS
    ctx = {"value_profile": value_profile, "commandments": commandments}
    takes: list[dict] = []
    used: set[str] = set()
    for m in panel:
        picked = _pick(principles, m.prefers, used) if m.prefers else []
        stance, take, drew = m.arguer(picked, ctx)
        for k in drew:
            used.add(k)
        takes.append({"mind": m.name, "lens": m.lens, "bias": m.bias,
                      "stance": stance, "take": take, "draws_on": drew})

    fors = [t for t in takes if t["stance"] == FOR]
    opposed = [t for t in takes if t["stance"] in _OPPOSE]
    split = bool(fors) and bool(opposed)
    # The sharpest dissent: a grounded objection if there is one, else the Critic.
    dissent = next((t for t in opposed if t["draws_on"]),
                   next((t for t in opposed if t["mind"] == "Critic"),
                        opposed[0] if opposed else None))

    return {
        "question": question,
        "takes": takes,
        "stance_counts": {
            "for": len(fors),
            "against_or_caution": len(opposed),
            "depends": sum(1 for t in takes if t["stance"] == DEPENDS),
            "reframe": sum(1 for t in takes if t["stance"] == REFRAME),
        },
        "split": split,
        "dissent": {"mind": dissent["mind"], "take": dissent["take"]} if dissent else None,
        "synthesis": _synthesis(fors, opposed, split, dissent, commandments, value_profile),
    }


def _synthesis(fors, opposed, split, dissent, commandments, value_profile) -> str:
    top = commandments[0]["statement"] if commandments else None
    if split:
        lead = f"The council is split — {len(fors)} would act, {len(opposed)} urge caution."
        if dissent:
            lead += f" The objection to take seriously — {dissent['mind']}: “{dissent['take']}”"
    elif fors and not opposed:
        lead = "The council leans toward acting — no mind flags a clear dealbreaker."
    elif opposed and not fors:
        lead = "The council leans cautious — slow down before you commit."
    else:
        lead = "The council is undecided on the facts you've recorded so far."
    if top:
        tie = f" Tiebreaker — your own principle: “{top}”."
    elif value_profile:
        tie = f" When it's close, choose what honours what you value: {', '.join(value_profile[:3])}."
    else:
        tie = " Nothing recorded yet to break the tie — make the call, then journal why."
    return lead + tie


# --- DB adapter -------------------------------------------------------------
def build(db, question: str, use_llm: bool = True) -> dict:
    """Convene the council on `question`, grounded in your principles & values."""
    from . import philosophy_engine, principle_engine

    principles = philosophy_engine._load_principles(db)
    commandments = principle_engine.commandments(principles)
    value_profile: list[str] = []
    try:
        from . import you_model
        value_profile = (you_model.build(db) or {}).get("value_profile", [])
    except Exception:
        value_profile = []

    result = deliberate(question, principles, value_profile, commandments)

    narrative = None
    generated_by = "deterministic"
    if use_llm:
        try:
            from . import llm
            if llm.available():
                lenses = "\n".join(
                    f"- {t['mind']} ({t['bias']}, leans {t['stance']}): {t['take']}"
                    for t in result["takes"])
                prompt = (
                    f"Question: {question}\n\nTen advisors — each with a DIFFERENT bias, and "
                    f"they disagree on purpose — argued:\n{lenses}\n\n"
                    "As chair, give an honest second-person ('you') verdict in 3-4 sentences. "
                    "Name where the council genuinely disagrees, take the strongest objection "
                    "seriously rather than smoothing it over, and end with the one thing you'd "
                    "actually do. Use only what the advisors said; don't invent facts."
                )
                out = llm.complete(
                    "You chair a council of clashing advisors and turn their disagreement "
                    "into wise, decisive, grounded counsel.", prompt,
                    max_tokens=260, temperature=0.6)
                if out and out.strip():
                    narrative = out.strip()
                    generated_by = "llm"
        except Exception:
            narrative = None

    return {
        "generated_at": _now_iso(),
        "ready": True,
        "question": question,
        "panel": [t["mind"] for t in result["takes"]],
        "takes": result["takes"],
        "stance_counts": result["stance_counts"],
        "split": result["split"],
        "dissent": result["dissent"],
        "synthesis": narrative or result["synthesis"],
        "generated_by": generated_by,
    }
