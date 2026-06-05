"""Seed PRL with a fully SYNTHETIC demo persona — safe for a public demo.

This invents a fictional life ("Alex Kumar") so every cortex and Reality-OS engine
lights up, with zero real personal data. NEVER seed a public/demo deployment from
the real DB dump or your git repos — use this.

    # validate the dataset WITHOUT a database (host-safe):
    python scripts/seed_demo.py --check

    # actually seed (needs DATABASE_URL pointing at the demo Postgres):
    DATABASE_URL=postgresql+psycopg://user:pass@host:5432/db \
      NEO4J_ENABLED=false python -m scripts.seed_demo

The dataset builder ``demo_specs()`` is pure (plain dicts) so it can be checked
offline; ``main()`` lazily imports the Memory Engine to ingest it.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _dt(y, m, d, h=10) -> str:
    return datetime(y, m, d, h, tzinfo=timezone.utc).isoformat()


def demo_specs() -> list[dict]:
    """A fictional, richly-cross-domain life as plain memory specs."""
    S: list[dict] = []

    # --- Milestone events (events / fractal / time machine / importance) -----
    S += [
        {"ts": _dt(2019, 6, 12), "source": "note", "title": "Graduated college",
         "content": "Finished my CS degree. Proud and a little terrified.",
         "importance": 0.9, "emotion": "proud", "memory_type": "episodic",
         "entities": [("person", "Mom"), ("person", "Dad")]},
        {"ts": _dt(2020, 9, 1), "source": "note", "title": "First job at Nimbus",
         "content": "Started as a backend engineer at Nimbus.",
         "importance": 0.85, "emotion": "excited", "memory_type": "episodic",
         "entities": [("project", "Nimbus"), ("skill", "Python")]},
        {"ts": _dt(2023, 11, 4), "source": "note", "title": "Trip to Goa",
         "content": "A week in Goa with Sam and Anita. Beaches, seafood, calm.",
         "importance": 0.7, "emotion": "joy", "memory_type": "episodic",
         "location": {"place": "Goa"},
         "entities": [("person", "Sam"), ("person", "Anita"), ("place", "Goa")]},
        {"ts": _dt(2025, 12, 14), "source": "note", "title": "Anita's wedding",
         "content": "My sister Anita got married. 48 guests, dancing, the whole family.",
         "importance": 0.97, "emotion": "joy", "memory_type": "social",
         "entities": [("person", "Anita"), ("person", "Mom"), ("person", "Dad")]},
    ]

    # --- Finance cortex (recurring rent/electricity, salary, an anomaly) ------
    for i, (y, m) in enumerate([(2026, 1), (2026, 2), (2026, 3), (2026, 4), (2026, 5)]):
        S.append({"ts": _dt(y, m, 1), "source": "bank", "title": f"Salary {y}-{m:02d}",
                  "content": "Monthly salary credited.", "importance": 0.5,
                  "memory_type": "episodic",
                  "meta": {"finance": [{"date": _dt(y, m, 1)[:10], "amount": 90000,
                                        "currency": "INR", "category": "salary",
                                        "kind": "income"}]}})
        S.append({"ts": _dt(y, m, 3), "source": "bank", "title": f"Rent {y}-{m:02d}",
                  "content": "Rent paid.", "importance": 0.4, "memory_type": "episodic",
                  "meta": {"finance": [{"date": _dt(y, m, 3)[:10], "amount": 28000,
                                        "currency": "INR", "category": "rent",
                                        "merchant": "Landlord", "kind": "expense"}]}})
        S.append({"ts": _dt(y, m, 5), "source": "bank", "title": f"Electricity {y}-{m:02d}",
                  "content": "Electricity bill.", "importance": 0.3, "memory_type": "episodic",
                  "meta": {"finance": [{"date": _dt(y, m, 5)[:10], "amount": 1800 + i * 50,
                                        "currency": "INR", "category": "utilities",
                                        "merchant": "PowerCo", "kind": "expense"}]}})
        S.append({"ts": _dt(y, m, 9), "source": "bank", "title": f"Groceries {y}-{m:02d}",
                  "content": "Groceries.", "importance": 0.3, "memory_type": "episodic",
                  "meta": {"finance": [{"date": _dt(y, m, 9)[:10], "amount": 6000,
                                        "currency": "INR", "category": "food",
                                        "kind": "expense"}]}})
    # A spending anomaly.
    S.append({"ts": _dt(2026, 3, 18), "source": "bank", "title": "New laptop",
              "content": "Bought a laptop for work.", "importance": 0.5,
              "memory_type": "episodic",
              "meta": {"finance": [{"date": "2026-03-18", "amount": 140000,
                                    "currency": "INR", "category": "electronics",
                                    "merchant": "TechStore", "kind": "expense"}]}})

    # --- Health cortex (meds, visits, lab trend) -----------------------------
    for m, val in [(1, 110), (3, 102), (5, 96)]:
        S.append({"ts": _dt(2026, m, 7), "source": "health",
                  "title": f"Blood sugar reading {2026}-{m:02d}",
                  "content": "Routine check.", "importance": 0.6, "memory_type": "episodic",
                  "meta": {"health": [{"date": _dt(2026, m, 7)[:10], "kind": "test",
                                       "test": "blood sugar", "value": val, "unit": "mg/dL"}]}})
    S.append({"ts": _dt(2026, 2, 14), "source": "health", "title": "Dr Sharma visit",
              "content": "Annual checkup with Dr Sharma; prescribed Metformin.",
              "importance": 0.65, "memory_type": "episodic",
              "entities": [("person", "Dr Sharma")],
              "meta": {"health": [{"date": "2026-02-14", "kind": "visit", "doctor": "Dr Sharma"},
                                  {"date": "2026-02-14", "kind": "medication",
                                   "medicine": "Metformin", "dose": "500mg"}]}})

    # --- Family cortex (relations, recipe, birthday) -------------------------
    S.append({"ts": _dt(2024, 5, 20), "source": "note", "title": "Mom's biryani recipe",
              "content": "Mom shared her biryani recipe — saffron, slow-cooked.",
              "importance": 0.7, "memory_type": "social", "entities": [("person", "Mom")],
              "meta": {"family": [{"relation": "mother", "name": "Priya"},
                                  {"kind": "recipe", "title": "Mom's biryani"}]}})
    S.append({"ts": _dt(2024, 8, 2), "source": "note", "title": "Dad's birthday",
              "content": "Celebrated Dad's birthday.", "importance": 0.6,
              "memory_type": "social", "entities": [("person", "Dad")],
              "meta": {"family": [{"relation": "father", "name": "Raj"},
                                  {"kind": "date", "label": "birthday", "month": 8, "day": 2}]}})

    # --- Emotional cortex (positive history, recent stress cluster) ----------
    for d in range(1, 16):
        S.append({"ts": _dt(2026, 1, d, 21), "source": "journal",
                  "title": f"Good day {d}", "content": "Felt content and focused.",
                  "importance": 0.3, "emotion": "content", "memory_type": "episodic"})
    for d in range(1, 6):
        S.append({"ts": _dt(2026, 5, 20 + d, 22), "source": "journal",
                  "title": f"Crunch day {d}", "content": "Deadline pressure, stressed.",
                  "importance": 0.4, "emotion": "stress", "memory_type": "episodic"})

    # --- Behaviour cortex (night-owl routine across many days) ---------------
    base = datetime(2026, 4, 1, tzinfo=timezone.utc)
    for day in range(20):
        for hr in (22, 23, 0):
            t = base + timedelta(days=day, hours=hr)
            S.append({"ts": t.isoformat(), "source": "git",
                      "title": f"Late commit d{day}h{hr}", "content": "Coding at night.",
                      "importance": 0.35, "memory_type": "knowledge",
                      "entities": [("project", "Aurora"), ("skill", "Python")]})

    # --- Goals / Dreams (identity, personal OS, dream cortex) ----------------
    S += [
        {"ts": _dt(2026, 1, 2), "source": "text", "title": "Goal: ship Aurora",
         "content": "I want to ship Aurora to production this year.",
         "importance": 0.7, "memory_type": "goal", "entities": [("goal", "ship Aurora")]},
        {"ts": _dt(2026, 1, 2), "source": "capture", "title": "Ambition",
         "content": "I want to build a company that helps people remember their lives.",
         "importance": 0.6, "memory_type": "goal",
         "entities": [("goal", "build a company that helps people remember their lives")],
         "meta": {"capture_kind": "ambition"}},
    ]
    return S


def _summary(specs: list[dict]) -> dict:
    from collections import Counter
    kinds = Counter()
    for s in specs:
        m = s.get("meta", {})
        if m.get("finance"):
            kinds["finance"] += 1
        if m.get("health"):
            kinds["health"] += 1
        if m.get("family"):
            kinds["family"] += 1
        if s.get("emotion"):
            kinds["emotion"] += 1
        if any(e[0] == "goal" for e in s.get("entities", [])):
            kinds["goal"] += 1
        if any(e[0] == "person" for e in s.get("entities", [])):
            kinds["person"] += 1
    return {"memories": len(specs), **dict(kinds)}


def main() -> None:
    specs = demo_specs()
    if "--check" in sys.argv:
        print("Synthetic demo dataset:", _summary(specs))
        # Sanity: every cortex must have something to show.
        s = _summary(specs)
        for need in ("finance", "health", "family", "emotion", "goal", "person"):
            assert s.get(need, 0) > 0, f"demo data missing {need}"
        print("OK — all cortexes covered, no real data.")
        return

    from app.db import SessionLocal, init_db
    from app.memory_engine import EntityRef, MemoryInput, ingest

    init_db()
    db = SessionLocal()
    created = 0
    try:
        for s in specs:
            mem = ingest(db, MemoryInput(
                ts=datetime.fromisoformat(s["ts"]),
                source=s["source"],
                title=s["title"],
                content=s.get("content", ""),
                importance=s.get("importance", 0.5),
                emotion=s.get("emotion"),
                location=s.get("location"),
                memory_type=s.get("memory_type"),
                entities=[EntityRef(type=t, name=n) for t, n in s.get("entities", [])],
                meta=s.get("meta", {}),
            ))
            if mem is not None:
                created += 1
    finally:
        db.close()
    print(f"Seeded {created} synthetic memories (demo persona 'Alex Kumar').")


if __name__ == "__main__":
    main()
