"""Family Cortex (Ledger).

Preserves the things that usually vanish: who's who, the stories and recipes,
and the dates that matter (birthdays, anniversaries) — with the next occurrence
and a gentle reminder when one is near. Pure ``analyze`` is DB-free and
unit-testable; ``build(db)`` reads family facts mined into memory metadata and
the ``person`` entities already in the Life Graph.

Preserves, never embellishes — it keeps what was actually said.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone


@dataclass
class FamilyFact:
    date: date                       # when this was recorded
    person: str
    relation: str = ""               # mother, father, grandmother, ...
    kind: str = "note"               # story | recipe | event | date | note
    detail: str = ""
    recur_month: int | None = None   # for kind == "date" (birthday/anniversary)
    recur_day: int | None = None


def _conf(n: int, scale: float, base: float = 0.3, cap: float = 0.9) -> float:
    return round(min(cap, base + n / scale), 2)


def _next_occurrence(month: int, day: int, today: date) -> date:
    """Next calendar occurrence of a month/day on or after today."""
    year = today.year
    try:
        cand = date(year, month, day)
    except ValueError:  # e.g. Feb 29 → treat as Mar 1
        cand = date(year, month, 28)
    if cand < today:
        try:
            cand = date(year + 1, month, day)
        except ValueError:
            cand = date(year + 1, month, 28)
    return cand


def analyze(facts: list[FamilyFact], today: date | None = None) -> dict:
    today = today or datetime.now(timezone.utc).date()
    if not facts:
        return {"ready": False, "message": "No family memories preserved yet."}

    # --- Relationship map ---
    people: dict[str, dict] = {}
    for f in facts:
        if not f.person:
            continue
        p = people.setdefault(f.person.strip(), {
            "person": f.person.strip(), "relation": f.relation, "mentions": 0, "kinds": {},
        })
        p["mentions"] += 1
        if f.relation and not p["relation"]:
            p["relation"] = f.relation
        p["kinds"][f.kind] = p["kinds"].get(f.kind, 0) + 1
    relationships = sorted(people.values(), key=lambda p: -p["mentions"])

    # --- Preserved stories / recipes / events ---
    stories = [
        {"person": f.person, "relation": f.relation, "kind": f.kind,
         "detail": f.detail, "recorded": f.date.isoformat()}
        for f in facts if f.kind in ("story", "recipe", "event", "note") and f.detail
    ]

    # --- Important recurring dates ---
    important_dates = []
    for f in facts:
        if f.kind == "date" and f.recur_month and f.recur_day:
            nxt = _next_occurrence(f.recur_month, f.recur_day, today)
            important_dates.append({
                "person": f.person,
                "relation": f.relation,
                "occasion": f.detail or "date",
                "month": f.recur_month,
                "day": f.recur_day,
                "next_occurrence": nxt.isoformat(),
                "days_until": (nxt - today).days,
            })
    important_dates.sort(key=lambda d: d["days_until"])

    # --- Reminders for dates coming up soon ---
    reminders = [
        {"type": "upcoming_date",
         "detail": f"{d['occasion']}" + (f" ({d['person']})" if d["person"] else "") + f" in {d['days_until']} days.",
         "priority": round(max(0.0, 1 - d["days_until"] / 30), 2)}
        for d in important_dates if 0 <= d["days_until"] <= 30
    ]

    explanation = (
        f"{len(relationships)} family member(s), {len(stories)} preserved "
        f"story/recipe item(s), {len(important_dates)} important date(s)."
    )

    return {
        "ready": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "confidence": _conf(len(facts), 15),
        "relationships": relationships,
        "stories": stories,
        "important_dates": important_dates,
        "reminders": reminders,
        "explanation": explanation,
    }


# --- DB adapter -------------------------------------------------------------
def build(db) -> dict:
    from sqlalchemy import select
    from .models import Memory

    rows = db.execute(
        select(Memory.ts, Memory.meta).where(Memory.meta.has_key("family"))  # noqa: W601
    ).all()

    facts: list[FamilyFact] = []
    for ts, meta in rows:
        for r in (meta or {}).get("family", []):
            try:
                d = date.fromisoformat(r["date"]) if r.get("date") else ts.date()
                facts.append(FamilyFact(
                    date=d,
                    person=r.get("person", ""),
                    relation=r.get("relation", ""),
                    kind=r.get("kind", "note"),
                    detail=r.get("detail", ""),
                    recur_month=r.get("recur_month"),
                    recur_day=r.get("recur_day"),
                ))
            except (KeyError, ValueError, TypeError):
                continue
    return analyze(facts)
