"""Finance Cortex (Ledger).

Turns scattered money signals — expenses, income, bills — into understanding:
spend trend, where the money goes, which payments recur (and when the next one
is due), the savings rate, and anything unusual. Pure ``analyze`` is DB-free and
unit-testable; ``build(db)`` is the adapter that reads finance records mined into
memory metadata.

Measures, never moralises. Below-threshold signals emit nothing (no fabrication).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from statistics import median

ANOMALY_FACTOR = 2.5  # an expense this many× the category's median reads as unusual


@dataclass
class Transaction:
    date: date
    amount: float                 # always positive; direction is `kind`
    currency: str = "INR"
    category: str = "uncategorised"
    merchant: str = ""
    kind: str = "expense"         # "expense" | "income"


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


def _conf(n: int, scale: float, base: float = 0.3, cap: float = 0.9) -> float:
    return round(min(cap, base + n / scale), 2)


def _month(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _cadence_label(days: float) -> str:
    if days <= 0:
        return "irregular"
    if days <= 9:
        return "weekly"
    if days <= 16:
        return "fortnightly"
    if days <= 45:
        return "monthly"
    if days <= 100:
        return "quarterly"
    if days <= 200:
        return "half-yearly"
    return "yearly"


def _detect_recurring(txns: list[Transaction], today: date) -> list[dict]:
    """Group expenses by payee and flag stable, repeating payments + next due."""
    groups: dict[str, list[Transaction]] = {}
    for t in txns:
        if t.kind != "expense":
            continue
        key = (t.merchant or t.category).strip().lower()
        if key:
            groups.setdefault(key, []).append(t)

    recurring: list[dict] = []
    for key, items in groups.items():
        if len(items) < 2:
            continue
        items = sorted(items, key=lambda t: t.date)
        amounts = [t.amount for t in items]
        m = _mean(amounts)
        # Amounts must be stable to count as the *same* recurring bill.
        if m <= 0 or (max(amounts) - min(amounts)) > 0.25 * m:
            continue
        gaps = [(items[i].date - items[i - 1].date).days for i in range(1, len(items))]
        gaps = [g for g in gaps if g > 0]
        if not gaps:
            continue
        cadence = median(gaps)
        last = items[-1].date
        next_due = last + timedelta(days=round(cadence))
        recurring.append({
            "payee": items[0].merchant or items[0].category,
            "category": items[0].category,
            "typical_amount": round(m, 2),
            "currency": items[0].currency,
            "cadence": _cadence_label(cadence),
            "cadence_days": round(cadence),
            "occurrences": len(items),
            "last_paid": last.isoformat(),
            "next_due": next_due.isoformat(),
            "days_until_due": (next_due - today).days,
            "confidence": _conf(len(items), 6, base=0.4),
        })
    recurring.sort(key=lambda r: r["days_until_due"])
    return recurring


def _anomalies(txns: list[Transaction]) -> list[dict]:
    """Per-category expenses far above the category's typical (median) spend.

    Uses the median, not the mean — a single large outlier inflates the mean (and
    std) enough to hide itself in small samples, so median is the robust baseline.
    """
    by_cat: dict[str, list[Transaction]] = {}
    for t in txns:
        if t.kind == "expense":
            by_cat.setdefault(t.category, []).append(t)
    out: list[dict] = []
    for cat, items in by_cat.items():
        if len(items) < 3:
            continue
        med = median([t.amount for t in items])
        if med <= 0:
            continue
        for t in items:
            if t.amount > ANOMALY_FACTOR * med:
                ratio = round(t.amount / med, 1)
                out.append({
                    "category": cat,
                    "merchant": t.merchant,
                    "amount": round(t.amount, 2),
                    "currency": t.currency,
                    "date": t.date.isoformat(),
                    "vs_typical": ratio,
                    "note": f"{ratio}× your typical {cat} spend",
                })
    out.sort(key=lambda a: -a["vs_typical"])
    return out


def analyze(txns: list[Transaction], today: date | None = None) -> dict:
    today = today or datetime.now(timezone.utc).date()
    if not txns:
        return {"ready": False, "message": "No financial activity recorded yet."}

    expenses = [t for t in txns if t.kind == "expense"]
    income = [t for t in txns if t.kind == "income"]
    total_exp = sum(t.amount for t in expenses)
    total_inc = sum(t.amount for t in income)
    net = total_inc - total_exp
    savings_rate = round(net / total_inc, 3) if total_inc > 0 else None

    # Monthly expense series + direction.
    monthly: dict[str, float] = {}
    for t in expenses:
        monthly[_month(t.date)] = monthly.get(_month(t.date), 0.0) + t.amount
    months_sorted = sorted(monthly.items())
    spend_series = [round(v, 2) for _, v in months_sorted]
    if len(spend_series) >= 2:
        recent = _mean(spend_series[-2:])
        earlier = _mean(spend_series[:-2]) if len(spend_series) > 2 else spend_series[0]
        diff = recent - earlier
        trend = "rising" if diff > 0.1 * (earlier or 1) else "falling" if diff < -0.1 * (earlier or 1) else "steady"
    else:
        trend = "insufficient history"

    # Top spend categories.
    by_cat: dict[str, float] = {}
    for t in expenses:
        by_cat[t.category] = by_cat.get(t.category, 0.0) + t.amount
    top_categories = [
        {"category": c, "total": round(v, 2), "share": round(v / total_exp, 3) if total_exp else 0.0}
        for c, v in sorted(by_cat.items(), key=lambda kv: -kv[1])
    ][:8]

    recurring = _detect_recurring(txns, today)
    anomalies = _anomalies(txns)
    upcoming = [r for r in recurring if 0 <= r["days_until_due"] <= 14]

    cur = txns[0].currency
    parts = [f"{len(txns)} transactions tracked"]
    if total_exp:
        parts.append(f"{cur} {round(total_exp):,} spent")
    if savings_rate is not None:
        parts.append(f"savings rate {round(savings_rate * 100)}%")
    if top_categories:
        parts.append(f"top category: {top_categories[0]['category']}")
    explanation = "; ".join(parts) + "."

    return {
        "ready": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "currency": cur,
        "confidence": _conf(len(txns), 30),
        "totals": {"income": round(total_inc, 2), "expense": round(total_exp, 2), "net": round(net, 2)},
        "savings_rate": savings_rate,
        "spend_trend": {"direction": trend, "monthly": [{"month": m, "spend": v} for (m, _), v in zip(months_sorted, spend_series)]},
        "top_categories": top_categories,
        "recurring_payments": recurring,
        "upcoming_bills": upcoming,
        "anomalies": anomalies,
        "explanation": explanation,
    }


# --- DB adapter -------------------------------------------------------------
def build(db) -> dict:
    """Read finance records mined into memory metadata and analyse them."""
    from sqlalchemy import select
    from .models import Memory

    rows = db.execute(
        select(Memory.ts, Memory.meta).where(Memory.meta.has_key("finance"))  # noqa: W601
    ).all()

    txns: list[Transaction] = []
    for ts, meta in rows:
        for r in (meta or {}).get("finance", []):
            try:
                d = date.fromisoformat(r["date"]) if r.get("date") else ts.date()
                txns.append(Transaction(
                    date=d,
                    amount=float(r["amount"]),
                    currency=r.get("currency", "INR"),
                    category=r.get("category", "uncategorised"),
                    merchant=r.get("merchant", ""),
                    kind=r.get("kind", "expense"),
                ))
            except (KeyError, ValueError, TypeError):
                continue
    return analyze(txns)
