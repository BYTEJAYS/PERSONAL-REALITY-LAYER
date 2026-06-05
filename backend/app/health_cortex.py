"""Health Cortex (Ledger).

Keeps a person's medical history coherent: active medications, doctor visits,
how test results trend over time, and the reminders that fall out of all that
(refills, overdue check-ups). Pure ``analyze`` is DB-free and unit-testable;
``build(db)`` reads health records mined into memory metadata.

Informational only — it organises records and surfaces reminders. It does not
diagnose or give medical advice.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone


@dataclass
class HealthEvent:
    date: date
    kind: str                # prescription | medicine | test | visit | symptom
    name: str                # medicine name, test name, doctor, or symptom
    value: float | None = None   # numeric test result, if any
    unit: str = ""
    doctor: str = ""


CHECKUP_DUE_DAYS = 180       # nudge a check-up if none in ~6 months
MED_ACTIVE_DAYS = 90         # a medicine seen within this window is "active"


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _conf(n: int, scale: float, base: float = 0.3, cap: float = 0.9) -> float:
    return round(min(cap, base + n / scale), 2)


def _days(a: date, b: date) -> int:
    return (a - b).days


def analyze(events: list[HealthEvent], today: date | None = None) -> dict:
    today = today or datetime.now(timezone.utc).date()
    if not events:
        return {"ready": False, "message": "No health records yet."}

    events = sorted(events, key=lambda e: e.date)

    # --- Medications (prescription / medicine mentions) ---
    meds: dict[str, list[HealthEvent]] = {}
    for e in events:
        if e.kind in ("prescription", "medicine") and e.name:
            meds.setdefault(e.name.strip(), []).append(e)
    medications = []
    for name, evs in sorted(meds.items()):
        last = evs[-1].date
        idle = _days(today, last)
        medications.append({
            "name": name,
            "status": "active" if idle <= MED_ACTIVE_DAYS else "past",
            "mentions": len(evs),
            "last_seen": last.isoformat(),
            "days_since": idle,
            "prescriber": next((e.doctor for e in reversed(evs) if e.doctor), ""),
        })
    medications.sort(key=lambda m: (m["status"] != "active", m["days_since"]))

    # --- Doctor visits ---
    visits = [e for e in events if e.kind == "visit"]
    doctors: dict[str, dict] = {}
    for v in visits:
        who = (v.doctor or v.name or "Doctor").strip()
        d = doctors.setdefault(who, {"doctor": who, "visits": 0, "last_visit": None})
        d["visits"] += 1
        d["last_visit"] = v.date.isoformat()
    last_visit = visits[-1].date if visits else None

    # --- Test result trends (numeric values over time) ---
    tests: dict[str, list[HealthEvent]] = {}
    for e in events:
        if e.kind == "test" and e.value is not None and e.name:
            tests.setdefault(e.name.strip(), []).append(e)
    test_trends = []
    for name, evs in sorted(tests.items()):
        evs = sorted(evs, key=lambda e: e.date)
        series = [{"date": e.date.isoformat(), "value": e.value, "unit": e.unit} for e in evs]
        if len(evs) >= 2:
            recent = _mean([e.value for e in evs[-2:]])
            earlier = _mean([e.value for e in evs[:-2]]) if len(evs) > 2 else evs[0].value
            diff = recent - earlier
            direction = "rising" if diff > 0.05 * abs(earlier or 1) else "falling" if diff < -0.05 * abs(earlier or 1) else "stable"
        else:
            direction = "single reading"
        test_trends.append({"name": name, "direction": direction, "latest": evs[-1].value,
                            "unit": evs[-1].unit, "readings": series})

    # --- Reminders ---
    reminders = []
    if last_visit is not None:
        since = _days(today, last_visit)
        if since >= CHECKUP_DUE_DAYS:
            reminders.append({
                "type": "checkup_due",
                "detail": f"No doctor visit in {since} days — a check-up may be overdue.",
                "priority": round(min(1.0, since / 365), 2),
            })
    for m in medications:
        # An active medicine not seen in a while may be due for a refill.
        if m["status"] == "active" and 30 <= m["days_since"] <= MED_ACTIVE_DAYS:
            reminders.append({
                "type": "refill_check",
                "detail": f"{m['name']} last noted {m['days_since']} days ago — check if a refill is due.",
                "priority": round(m["days_since"] / MED_ACTIVE_DAYS, 2),
            })
    reminders.sort(key=lambda r: -r["priority"])

    active_meds = sum(1 for m in medications if m["status"] == "active")
    explanation = (
        f"{len(events)} health records: {active_meds} active medication(s), "
        f"{len(visits)} visit(s), {len(test_trends)} tracked test(s)."
    )

    return {
        "ready": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "confidence": _conf(len(events), 20),
        "medications": medications,
        "doctors": list(doctors.values()),
        "last_visit": last_visit.isoformat() if last_visit else None,
        "test_trends": test_trends,
        "reminders": reminders,
        "explanation": explanation,
        "disclaimer": "Informational record-keeping only — not medical advice.",
    }


# --- DB adapter -------------------------------------------------------------
def build(db) -> dict:
    from sqlalchemy import select
    from .models import Memory

    rows = db.execute(
        select(Memory.ts, Memory.meta).where(Memory.meta.has_key("health"))  # noqa: W601
    ).all()

    events: list[HealthEvent] = []
    for ts, meta in rows:
        for r in (meta or {}).get("health", []):
            try:
                d = date.fromisoformat(r["date"]) if r.get("date") else ts.date()
                val = r.get("value")
                events.append(HealthEvent(
                    date=d,
                    kind=r.get("kind", "visit"),
                    name=r.get("name", ""),
                    value=float(val) if val is not None else None,
                    unit=r.get("unit", ""),
                    doctor=r.get("doctor", ""),
                ))
            except (KeyError, ValueError, TypeError):
                continue
    return analyze(events)
