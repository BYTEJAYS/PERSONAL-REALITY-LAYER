"""Memory Versioning — Git for human reality (Reality OS).

Reality changes; old truths are never overwritten, only superseded. A versioned
fact keeps the full history of an attribute's values over time (favourite
language: Python → Rust → Julia), so PRL can answer "what was true *then*" as well
as "what is true now". Every edge of truth carries when it became valid.

Pure functions are DB-free and unit-testable; ``build(db)`` assembles version
chains from facts recorded in memory metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dt(x) -> datetime:
    if isinstance(x, datetime):
        return x if x.tzinfo else x.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(x).replace(tzinfo=timezone.utc) if "T" in str(x) \
        else datetime.fromisoformat(str(x)).replace(tzinfo=timezone.utc)


@dataclass
class Version:
    value: str
    valid_from: datetime
    valid_to: datetime | None = None     # None = still current
    source: str = ""
    confidence: float = 0.5

    def as_dict(self) -> dict:
        return {
            "value": self.value,
            "valid_from": self.valid_from.isoformat(),
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
            "source": self.source,
            "confidence": self.confidence,
        }


@dataclass
class VersionedFact:
    attribute: str
    versions: list[Version] = field(default_factory=list)

    def record(self, value: str, valid_from, source: str = "", confidence: float = 0.5):
        """Append a new value ONLY when it differs from the current one (never
        overwrite). Closes the previous version's validity at the new start."""
        vf = _dt(valid_from)
        ordered = sorted(self.versions, key=lambda v: v.valid_from)
        if ordered and ordered[-1].value == value:
            return self  # unchanged truth — no new version
        if ordered:
            ordered[-1].valid_to = vf
        ordered.append(Version(value=value, valid_from=vf, source=source, confidence=confidence))
        self.versions = ordered
        return self

    def value_at(self, when) -> str | None:
        w = _dt(when)
        match = None
        for v in sorted(self.versions, key=lambda v: v.valid_from):
            if v.valid_from <= w and (v.valid_to is None or w < v.valid_to):
                match = v.value
        return match

    def current(self) -> str | None:
        return self.versions[-1].value if self.versions else None

    def timeline(self) -> list[dict]:
        return [v.as_dict() for v in sorted(self.versions, key=lambda v: v.valid_from)]


def build_fact(attribute: str, observations: list[tuple]) -> VersionedFact:
    """observations = [(value, valid_from, source, confidence), ...] in any order."""
    fact = VersionedFact(attribute=attribute)
    for obs in sorted(observations, key=lambda o: _dt(o[1])):
        value, vf = obs[0], obs[1]
        source = obs[2] if len(obs) > 2 else ""
        conf = obs[3] if len(obs) > 3 else 0.5
        fact.record(value, vf, source, conf)
    return fact


# --- DB adapter -------------------------------------------------------------
def build(db, attribute: str | None = None) -> dict:
    from sqlalchemy import select
    from .models import Memory

    rows = db.execute(
        select(Memory.ts, Memory.source, Memory.meta).where(Memory.meta.has_key("fact"))  # noqa: W601
    ).all()

    by_attr: dict[str, list[tuple]] = {}
    for ts, source, meta in rows:
        fact = (meta or {}).get("fact", {})
        attr, val = fact.get("attribute"), fact.get("value")
        if not attr or val is None:
            continue
        if attribute and attr != attribute:
            continue
        by_attr.setdefault(attr, []).append((str(val), ts, source or "", fact.get("confidence", 0.5)))

    facts = []
    for attr, obs in sorted(by_attr.items()):
        vf = build_fact(attr, obs)
        facts.append({
            "attribute": attr,
            "current": vf.current(),
            "versions": len(vf.versions),
            "timeline": vf.timeline(),
        })
    return {
        "ready": len(facts) > 0,
        "generated_at": _now().isoformat(),
        "tracked_attributes": len(facts),
        "facts": facts,
    }
