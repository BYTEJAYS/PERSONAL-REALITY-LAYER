"""Life-domain extraction for free text — feeds the Finance / Health / Family
cortexes the same way ``extract.py`` feeds the cognitive twin.

A pasted note ("paid ₹1200 electricity bill", "Dr. Sharma prescribed metformin",
"grandmother's biryani recipe", "mom's birthday on June 5") is mined into
structured, JSON-serialisable records that are stored on the memory's ``meta`` so
the cortex ``build(db)`` adapters can read them back.

Heuristic and conservative — every record is something explicitly stated in the
text, never inferred out of thin air. Pure functions, dependency-free, testable.
"""

from __future__ import annotations

import re
from datetime import date

_SENTENCE = re.compile(r"[.;\n!?]+")

# ---------------------------------------------------------------------------
# Shared date parsing
# ---------------------------------------------------------------------------
_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}
_MONTHS.update({m[:3]: i for m, i in list(_MONTHS.items())})

_DATE_MD = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)\b|\b([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?\b",
    re.IGNORECASE,
)


def _parse_monthday(text: str) -> tuple[int, int] | None:
    """Pull a (month, day) out of '5 June' / 'June 5' style text."""
    for m in _DATE_MD.finditer(text):
        if m.group(1) and m.group(2):          # "5 June"
            day, mon = int(m.group(1)), m.group(2).lower()
        elif m.group(3) and m.group(4):        # "June 5"
            mon, day = m.group(3).lower(), int(m.group(4))
        else:
            continue
        if mon in _MONTHS and 1 <= day <= 31:
            return _MONTHS[mon], day
    return None


def _parse_date(text: str, default: date) -> date:
    md = _parse_monthday(text)
    if not md:
        return default
    yr = default.year
    ym = re.search(r"\b(20\d{2})\b", text)
    if ym:
        yr = int(ym.group(1))
    try:
        return date(yr, md[0], md[1])
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# Finance
# ---------------------------------------------------------------------------
_AMOUNT = re.compile(
    r"(?:(₹|rs\.?|inr|\$)\s?([\d,]+(?:\.\d+)?))"
    r"|(?:([\d,]+(?:\.\d+)?)\s?(rupees|rs|dollars|usd))",
    re.IGNORECASE,
)
_INCOME_RX = re.compile(r"\b(received|salary|earned|income|got paid|refund|credited|deposit)\b", re.IGNORECASE)
_CATEGORIES: list[tuple[str, str]] = [
    ("rent", r"\brent\b"),
    ("utilities", r"\b(electricity|water bill|gas bill|utility|broadband|internet bill|wifi bill)\b"),
    ("groceries", r"\b(groceries|grocery|vegetables|supermarket|kirana)\b"),
    ("food", r"\b(food|dinner|lunch|restaurant|swiggy|zomato|cafe|coffee)\b"),
    ("fuel", r"\b(fuel|petrol|diesel|gas station)\b"),
    ("transport", r"\b(uber|ola|cab|taxi|metro|bus|train ticket|flight)\b"),
    ("subscription", r"\b(subscription|netflix|spotify|prime|youtube premium|hotstar)\b"),
    ("insurance", r"\b(insurance|premium|policy)\b"),
    ("loan", r"\b(emi|loan|mortgage|installment)\b"),
    ("medical", r"\b(medicine|pharmacy|hospital|doctor fee|clinic)\b"),
    ("shopping", r"\b(amazon|flipkart|shopping|clothes|myntra)\b"),
    ("education", r"\b(tuition|fees|course|college fee|school fee)\b"),
    ("bills", r"\bbill\b"),
]
_MERCHANTS = ["Netflix", "Spotify", "Amazon", "Flipkart", "Swiggy", "Zomato", "Uber",
              "Ola", "Jio", "Airtel", "Myntra", "Hotstar"]


def _to_float(s: str) -> float:
    return float(s.replace(",", ""))


def extract_finance(text: str, default_date: date) -> list[dict]:
    out: list[dict] = []
    for sentence in _SENTENCE.split(text):
        low = sentence.lower()
        for m in _AMOUNT.finditer(sentence):
            sym = (m.group(1) or m.group(4) or "").lower()
            amount = _to_float(m.group(2) or m.group(3))
            if amount <= 0:
                continue
            currency = "USD" if "$" in sym or "dollar" in sym or "usd" in sym else "INR"
            category = next((name for name, rx in _CATEGORIES if re.search(rx, low)), "uncategorised")
            merchant = next((mch for mch in _MERCHANTS if mch.lower() in low), "")
            kind = "income" if _INCOME_RX.search(low) else "expense"
            out.append({
                "date": _parse_date(sentence, default_date).isoformat(),
                "amount": amount, "currency": currency,
                "category": category, "merchant": merchant, "kind": kind,
            })
    return out


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
_DOCTOR = re.compile(r"\bdr\.?\s+([A-Z][a-zA-Z]+)", re.IGNORECASE)
_PRESCRIBED = re.compile(r"\b(?:prescribed|prescription for|taking|started on|put on)\s+([a-z][a-z0-9\-]+)", re.IGNORECASE)
_DOSE = re.compile(r"\b([a-z][a-z0-9\-]+)\s+\d+\s?(?:mg|ml|mcg|g)\b", re.IGNORECASE)
_VISIT = re.compile(r"\b(visited|saw|consulted|appointment with|checkup with|met)\b.*\bdr\.?\s+[A-Z]", re.IGNORECASE)
# Single-value numeric tests only. Blood pressure is deliberately excluded — it's
# a systolic/diastolic ratio (120/80), not a single trendable number, and parsing
# it as one produced junk values + units.
_TEST = re.compile(
    r"\b(blood sugar|sugar|glucose|cholesterol|hba1c|hemoglobin|haemoglobin|"
    r"weight|heart rate|vitamin d|tsh|creatinine)\b[^0-9]{0,12}(\d+(?:\.\d+)?)\s?(mg/dl|mmol/l|mg|g/dl|kg|bpm|%|ng/ml)?",
    re.IGNORECASE,
)
# Canonicalise aliases so the same test doesn't split into separate trends.
_TEST_CANON = {"sugar": "blood sugar", "glucose": "blood sugar", "haemoglobin": "hemoglobin"}


def extract_health(text: str, default_date: date) -> list[dict]:
    out: list[dict] = []
    for sentence in _SENTENCE.split(text):
        d = _parse_date(sentence, default_date).isoformat()
        doctor_m = _DOCTOR.search(sentence)
        doctor = doctor_m.group(1) if doctor_m else ""

        # Tests (single-value numeric readings).
        for m in _TEST.finditer(sentence):
            name = m.group(1).strip().lower()
            name = _TEST_CANON.get(name, name)
            try:
                value = float(m.group(2))
            except (TypeError, ValueError):
                continue
            out.append({"date": d, "kind": "test", "name": name,
                        "value": value, "unit": (m.group(3) or "").strip().lower(), "doctor": doctor})

        # Prescriptions / medicines.
        for rx in (_PRESCRIBED, _DOSE):
            for m in rx.finditer(sentence):
                med = m.group(1).strip().lower()
                if len(med) >= 3 and med not in ("the", "and", "for", "with"):
                    out.append({"date": d, "kind": "prescription" if rx is _PRESCRIBED else "medicine",
                                "name": med, "value": None, "unit": "", "doctor": doctor})

        # Visits.
        if _VISIT.search(sentence) and doctor:
            out.append({"date": d, "kind": "visit", "name": doctor,
                        "value": None, "unit": "", "doctor": doctor})
    # De-dup identical records.
    seen, uniq = set(), []
    for r in out:
        key = (r["date"], r["kind"], r["name"], r["value"])
        if key not in seen:
            seen.add(key)
            uniq.append(r)
    return uniq


# ---------------------------------------------------------------------------
# Family
# ---------------------------------------------------------------------------
_RELATIONS = {
    "mother": "mother", "mom": "mother", "mum": "mother", "amma": "mother",
    "father": "father", "dad": "father", "papa": "father",
    "grandmother": "grandmother", "grandma": "grandmother", "nani": "grandmother", "dadi": "grandmother",
    "grandfather": "grandfather", "grandpa": "grandfather", "nana": "grandfather", "dada": "grandfather",
    "sister": "sister", "brother": "brother",
    "wife": "wife", "husband": "husband", "son": "son", "daughter": "daughter",
    "aunt": "aunt", "uncle": "uncle", "cousin": "cousin",
}
_REL_RX = re.compile(r"\b(" + "|".join(sorted(_RELATIONS, key=len, reverse=True)) + r")\b", re.IGNORECASE)
_NAMED = re.compile(r"\b(?:my\s+)?(?:%s)\s+([A-Z][a-z]+)\b" % "|".join(_RELATIONS))
_OCCASION = re.compile(r"\b(birthday|anniversary|wedding day)\b", re.IGNORECASE)


def extract_family(text: str, default_date: date) -> list[dict]:
    out: list[dict] = []
    for sentence in _SENTENCE.split(text):
        rel_m = _REL_RX.search(sentence)
        if not rel_m:
            continue
        relation = _RELATIONS[rel_m.group(1).lower()]
        named = _NAMED.search(sentence)
        person = named.group(1) if named else relation
        low = sentence.lower()

        occ = _OCCASION.search(sentence)
        md = _parse_monthday(sentence)
        if occ and md:
            out.append({"date": default_date.isoformat(), "person": person, "relation": relation,
                        "kind": "date", "detail": occ.group(1).lower(),
                        "recur_month": md[0], "recur_day": md[1]})
            continue

        if "recipe" in low:
            kind = "recipe"
        elif re.search(r"\b(story|remember|used to|told me|grew up|back then|when (he|she|they))\b", low):
            kind = "story"
        elif re.search(r"\b(wedding|graduated|born|passed away|started|moved)\b", low):
            kind = "event"
        else:
            kind = "note"
        out.append({"date": default_date.isoformat(), "person": person, "relation": relation,
                    "kind": kind, "detail": sentence.strip()[:240],
                    "recur_month": None, "recur_day": None})
    return out


def extract_all(text: str, default_date: date) -> dict[str, list[dict]]:
    """Run all three life extractors; only include domains that found something."""
    result = {
        "finance": extract_finance(text, default_date),
        "health": extract_health(text, default_date),
        "family": extract_family(text, default_date),
    }
    return {k: v for k, v in result.items() if v}
