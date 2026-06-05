"""Personal World Model (Reality OS) — #14, PARTIAL → BUILT.

Beyond isolated memories, PRL keeps one living model of the user's life: a single
queryable snapshot of every domain — health, finance, family, social, emotional,
behaviour, knowledge, projects, goals — each with a status and a one-line read,
plus which domains are thriving and which are being neglected.

Pure ``assemble_world`` is DB-free and unit-testable; ``build(db)`` derives each
domain's health from its cortex/engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

DOMAINS = ("health", "finance", "family", "social", "emotional",
           "behaviour", "knowledge", "projects", "goals")

# How much each domain counts toward overall life coherence.
DOMAIN_WEIGHT = {d: 1.0 for d in DOMAINS}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def domain_status(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score >= 0.66:
        return "thriving"
    if score >= 0.4:
        return "stable"
    if score >= 0.2:
        return "at_risk"
    return "neglected"


@dataclass
class Domain:
    name: str
    score: float | None          # 0..1 health, or None if no data
    summary: str = ""

    def as_dict(self) -> dict:
        return {"domain": self.name, "score": self.score,
                "status": domain_status(self.score), "summary": self.summary}


@dataclass
class WorldState:
    domains: list[Domain] = field(default_factory=list)

    def as_dict(self) -> dict:
        known = [d for d in self.domains if d.score is not None]
        if known:
            wsum = sum(DOMAIN_WEIGHT.get(d.name, 1.0) for d in known)
            coherence = round(
                sum(d.score * DOMAIN_WEIGHT.get(d.name, 1.0) for d in known) / wsum, 3)
        else:
            coherence = None
        neglected = [d.name for d in self.domains
                     if domain_status(d.score) in ("neglected", "at_risk")]
        thriving = [d.name for d in known if domain_status(d.score) == "thriving"]
        return {
            "coherence": coherence,
            "domains_known": len(known),
            "domains_total": len(self.domains),
            "thriving": thriving,
            "neglected": neglected,
            "domains": [d.as_dict() for d in self.domains],
        }


def assemble_world(domain_inputs: dict) -> dict:
    """`domain_inputs` = {domain_name: {"score": 0..1|None, "summary": str}}.
    Missing domains are recorded as unknown so neglect is visible, not hidden."""
    domains = []
    for name in DOMAINS:
        info = domain_inputs.get(name) or {}
        domains.append(Domain(name, info.get("score"), info.get("summary", "")))
    return WorldState(domains).as_dict()


# --- DB adapter -------------------------------------------------------------
def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def build(db) -> dict:
    from . import (behaviour_cortex, emotional_cortex, family_cortex, finance_cortex,
                   health_cortex, social_cortex)
    from .brain import brain_state  # region intensities for projects/goals/knowledge

    def safe(fn, default=None):
        try:
            return fn()
        except Exception:
            return default

    inputs: dict = {}

    fin = safe(lambda: finance_cortex.build(db), {}) or {}
    if fin.get("ready"):
        sr = fin.get("savings_rate")
        inputs["finance"] = {"score": _clamp(0.5 + (sr or 0)) if sr is not None else 0.5,
                             "summary": fin.get("explanation", "")}

    hea = safe(lambda: health_cortex.build(db), {}) or {}
    if hea.get("ready"):
        inputs["health"] = {"score": 0.6, "summary": hea.get("explanation", "tracked")}

    fam = safe(lambda: family_cortex.build(db), {}) or {}
    if fam.get("ready"):
        inputs["family"] = {"score": 0.6, "summary": fam.get("explanation", "tracked")}

    soc = safe(lambda: social_cortex.build(db), {}) or {}
    if soc.get("ready"):
        n = len(soc.get("inner_circle", []))
        drift = len(soc.get("drifting", []))
        inputs["social"] = {"score": _clamp(0.3 + 0.1 * n - 0.05 * drift),
                            "summary": soc.get("explanation", "")}

    emo = safe(lambda: emotional_cortex.build(db), {}) or {}
    if emo.get("ready"):
        v = emo.get("overall_valence", 0.0)
        inputs["emotional"] = {"score": _clamp(0.5 + v / 2),
                              "summary": emo.get("explanation", "")}

    beh = safe(lambda: behaviour_cortex.build(db), {}) or {}
    if beh.get("ready"):
        inputs["behaviour"] = {"score": _clamp(beh.get("consistency", 0.0)),
                              "summary": beh.get("explanation", "")}

    bs = safe(lambda: brain_state(db), {}) or {}
    regions = {r["region"]: r.get("intensity", 0.0) for r in bs.get("regions", [])} \
        if isinstance(bs, dict) else {}
    for dom, region in (("knowledge", "knowledge"), ("projects", "project"), ("goals", "goal")):
        if region in regions:
            inputs[dom] = {"score": _clamp(regions[region]),
                           "summary": f"{region} activity"}

    world = assemble_world(inputs)
    world["generated_at"] = _now().isoformat()
    world["ready"] = world["domains_known"] > 0
    return world


def query(db, domain: str) -> dict:
    world = build(db)
    for d in world.get("domains", []):
        if d["domain"] == domain:
            return {"ready": True, "generated_at": world["generated_at"], **d}
    return {"ready": False, "error": f"unknown domain: {domain}"}
