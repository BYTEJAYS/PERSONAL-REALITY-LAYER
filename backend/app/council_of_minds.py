"""Council of Minds — ten reasoning lenses that deliberate on a question.

Where the Multi-Agent Society (``agents.py``) routes a query to the *data* engine
that can answer it, the Council of Minds applies ten distinct *ways of thinking*
to a dilemma — Scientist, Engineer, Historian, Entrepreneur, Philosopher, Critic,
Optimist, Strategist, Creative Thinker, Psychologist — and fuses them into a
single higher-order take.

Each mind reasons from YOUR own recorded wisdom: it cites the principles, values,
and patterns most relevant to its lens, so the advice is yours, not generic. It
works fully deterministically (each mind reframes the question through its lens and
grounds it in your principles); when the local model is up, an optional fused
``synthesis`` is narrated on top.

Pure ``deliberate`` is DB-free and unit-tested; ``build(db, question)`` gathers
your principles/values and convenes the council.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conviction(p: dict) -> float:
    return float(p.get("confidence", 0.0)) * math.log2(2 + int(p.get("evidence_count", 1)))


@dataclass
class Mind:
    name: str
    lens: str                       # one-line description of how this mind thinks
    prefers: tuple[str, ...]        # wisdom categories it draws on
    with_principle: str             # template when it has a grounded principle ({p})
    generic: str                    # fallback prompt when nothing grounds it
    uses_values: bool = False       # Philosopher leans on the value profile ({values})


MINDS: list[Mind] = [
    Mind("Scientist", "Weighs the evidence", ("growth_driver", "success_pattern", "pitfall"),
         "The best-evidenced pattern you have here: {p}. Decide by data, not gut.",
         "What does the evidence actually support? Don't trust a story you can't measure."),
    Mind("Critic", "Hunts the downside", ("pitfall", "lesson"),
         "Watch the failure mode — your history warns: {p}",
         "What's the failure mode you're not naming? Assume the optimistic case is wrong."),
    Mind("Optimist", "Sees the upside", ("success_pattern", "growth_driver"),
         "Lean into what works for you: {p}",
         "What would make this clearly worth it — and how do you get there?"),
    Mind("Strategist", "Plays the long game", ("philosophy",),
         "Think in decades: {p} Pick the path with the best decade, not the best week.",
         "Which choice has the better decade? Optimise the long arc, not the next month."),
    Mind("Philosopher", "Tests it against your values", ("philosophy",),
         "Does this honour what you value — {values}? If not, that's your answer.",
         "Does this align with who you want to be? Values first, tactics second.",
         uses_values=True),
    Mind("Psychologist", "Reads your patterns and feelings", ("lesson",),
         "Mind your pattern: {p} How you'll feel in a week matters more than today's mood.",
         "How will this actually feel — and which of your patterns is driving the urge?"),
    Mind("Historian", "Trusts the track record", ("success_pattern", "growth_driver", "lesson"),
         "You've been here before — {p} has held up. Trust the track record.",
         "When did you face this before, and what did that teach you?"),
    Mind("Entrepreneur", "Bets on asymmetric upside", ("growth_driver", "success_pattern"),
         "Bias to action on what compounds: {p} Asymmetric upside beats certainty.",
         "Where's the asymmetric bet — small cost, large possible payoff?"),
    Mind("Engineer", "Builds a reliable system", ("lesson", "growth_driver"),
         "Make it a system, not a willpower bet: {p}",
         "What's the simplest reliable system here, so it doesn't depend on motivation?"),
    Mind("Creative Thinker", "Finds the third option", (),
         "", "What's the option nobody's suggesting? Combine two things you already do well."),
]


def _pick(principles: list[dict], cats: tuple[str, ...], n: int = 1) -> list[dict]:
    pool = [p for p in principles
            if p.get("category") in cats and p.get("status") in ("active", "forming")]
    pool.sort(key=_conviction, reverse=True)
    return pool[:n]


def deliberate(question: str, principles: list[dict], value_profile: list[str],
               commandments: list[dict], minds: list[Mind] | None = None) -> dict:
    """Each mind weighs in (grounded in your principles), then a deterministic fuse."""
    panel = minds if minds is not None else MINDS
    takes: list[dict] = []
    used_keys: set[str] = set()
    for m in panel:
        draws: list[str] = []
        if m.uses_values and value_profile:
            take = m.with_principle.format(values=", ".join(value_profile[:3]))
        else:
            picked = _pick(principles, m.prefers) if m.prefers else []
            # avoid every mind citing the same one principle
            picked = [p for p in picked if p.get("key") not in used_keys] or picked
            if picked and m.with_principle:
                take = m.with_principle.format(p=picked[0]["statement"])
                draws = [picked[0]["key"]]
                used_keys.add(picked[0]["key"])
            else:
                take = m.generic
        takes.append({"mind": m.name, "lens": m.lens, "take": take, "draws_on": draws})

    return {"question": question, "takes": takes,
            "synthesis": _synthesis(takes, commandments, value_profile)}


def _synthesis(takes: list[dict], commandments: list[dict], value_profile: list[str]) -> str:
    grounded = [t for t in takes if t["draws_on"]]
    top = commandments[0]["statement"] if commandments else None
    if not grounded and not top:
        return ("Not enough recorded yet for a grounded verdict — treat the council's "
                "questions as prompts to think it through, then journal the call you make.")
    crit = next((t for t in takes if t["mind"] == "Critic" and t["draws_on"]), None)
    opt = next((t for t in takes if t["mind"] == "Optimist" and t["draws_on"]), None)
    parts = []
    if crit and opt:
        parts.append("Your own history both encourages and cautions here — weigh the upside "
                     "against the failure mode it names.")
    if top:
        parts.append(f"The throughline across the council is your principle: “{top}”.")
    elif value_profile:
        parts.append(f"When in doubt, choose what honours what you value: {', '.join(value_profile[:3])}.")
    return " ".join(parts)


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
                lenses = "\n".join(f"- {t['mind']} ({t['lens']}): {t['take']}" for t in result["takes"])
                prompt = (
                    f"Question: {question}\n\nTen advisors weighed in:\n{lenses}\n\n"
                    "As the chair of this council, fuse these into a single honest, "
                    "second-person ('you') verdict in 3-4 sentences. Ground it in what the "
                    "advisors said; don't invent facts about the person. End with the one "
                    "thing you'd actually do."
                )
                out = llm.complete(
                    "You chair a council of advisors and synthesise their views into wise, "
                    "grounded, decisive counsel.", prompt, max_tokens=240, temperature=0.6)
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
        "synthesis": narrative or result["synthesis"],
        "generated_by": generated_by,
    }
