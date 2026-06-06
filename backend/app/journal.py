"""Journal Mode — the daily-reflection connector that turns lived experience
into structured, learnable memory.

A journal entry is free text the user writes at the end of a day:

    Today I attended college. Worked on my ML project. Argued with my friend
    Rahul. Started reading about reinforcement learning. Felt stressed because
    of deadlines. Went to the gym. Watched Interstellar.

``extract_events`` (pure, DB-free, unit-testable) splits that into structured,
categorised events — each with a type, a one-line description, the people
involved, a detected emotion, and an importance score. ``add_entry`` then
stores the raw entry as a single ``journal`` memory (nothing is lost) whose
entities and dominant emotion are wired so the *existing* engines pick it up
for free: the emotion feeds the Emotional Cortex, people feed the Social
Cortex, skills/projects feed the Habit/Knowledge engines, goals populate the
goal region, and the memory itself joins the Timeline / Events / Patterns.

``journal`` is a PRIVATE source (see companion.PRIVATE_SOURCES) — the friend
voice never quotes it. It is the owner's own record.

Heuristic and conservative by design: every event is something the text
actually says; nothing is invented.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

from .emotional_cortex import valence

_SENTENCE = re.compile(r"(?<=[.!?;\n])\s+|\n+")

# --- Life-domain categories (the spec's twelve) -----------------------------
# Each category maps to a regex of cue words. A sentence is scored against all
# of them; the highest-scoring category wins (ties broken by declaration order).
CATEGORY_CUES: dict[str, str] = {
    "Work": r"\b(work(ed|ing)?|job|office|meeting|client|deadline|shipped|deploy(ed)?|boss|interview|task)\b",
    "Study": r"\b(study|studied|studying|learn(ed|ing)?|read(ing)?|course|lecture|college|class(es)?|exam|assignment|semester|notes|tutorial)\b",
    "Projects": r"\b(project|built|building|coding|code(d)?|app|feature|bug|debug(ged|ging)?|ml project|prototype|repo|commit)\b",
    "Relationships": r"\b(friend|argu(ed|ment)|fight|fought|hung out|hangout|date|girlfriend|boyfriend|partner|crush|met|call(ed)?|chat(ted)?|texted)\b",
    "Family": r"\b(family|mom|mum|dad|mother|father|parents?|brother|sister|grandmother|grandfather|grandma|grandpa|cousin|aunt|uncle|home)\b",
    "Fitness": r"\b(gym|workout|work ?out|run(ning)?|ran|exercise|football|cricket|lifting|cardio|walk(ed)?|jog(ged)?|sport)\b",
    "Health": r"\b(sick|ill|doctor|medicine|meds|sleep|slept|insomnia|headache|fever|rest(ed)?|nap|tired|diet|hospital)\b",
    "Finance": r"\b(bought|buy|paid|pay|money|spent|spend|invest(ed|ing)?|salary|expense|bill|rent|saved|saving|₹|rs\.?|\$)\b",
    "Entertainment": r"\b(watch(ed|ing)?|movie|film|anime|series|show|game|gaming|played|music|guitar|song|concert|netflix|youtube)\b",
    "Travel": r"\b(travel(led|ling)?|trip|flight|flew|went to|visit(ed)?|vacation|holiday|drove|train|journey)\b",
    "Personal Growth": r"\b(reflect(ed|ing)?|realis(ed|e)|realiz(ed|e)|goal|improve(d)?|meditat(e|ed|ion)|journal(ed|ing)?|habit|discipline|mindset)\b",
    "Emotions": r"\b(felt|feel(ing)?|emotion(al)?|mood|cried|crying|overwhelmed|breakdown)\b",
}
_CATEGORY_RX = {c: re.compile(p, re.IGNORECASE) for c, p in CATEGORY_CUES.items()}
_CATEGORY_ORDER = list(CATEGORY_CUES)

# --- Emotion detection ------------------------------------------------------
# Surface cue -> canonical emotion label (aligned with emotional_cortex labels
# where possible so valence() and the Emotional Cortex agree).
EMOTION_CUES: dict[str, str] = {
    "happy": "happy", "glad": "happy", "enjoyed": "happy", "fun": "happy", "good day": "happy",
    "excited": "excitement", "thrilled": "excitement", "can't wait": "excitement",
    "proud": "proud", "accomplished": "proud", "achieved": "proud",
    "grateful": "grateful", "thankful": "grateful", "blessed": "grateful",
    "motivated": "motivated", "driven": "motivated", "focused": "motivated",
    "curious": "curious", "intrigued": "curious", "fascinated": "curious",
    "confident": "confident", "sure of": "confident",
    "inspired": "inspired", "inspiring": "inspired",
    "calm": "calm", "peaceful": "calm", "relaxed": "calm", "content": "content",
    "hopeful": "hopeful",
    "stress": "stress", "stressed": "stress", "pressure": "stress", "deadline": "stress",
    "anxious": "anxious", "anxiety": "anxious", "nervous": "anxious", "worried": "anxious",
    "sad": "sad", "down": "sad", "unhappy": "sad", "depressed": "sad",
    "angry": "angry", "anger": "angry", "argued": "angry", "argument": "angry",
    "fight": "angry", "fought": "angry", "furious": "angry", "annoyed": "angry",
    "frustrated": "frustrated", "frustration": "frustrated", "stuck": "frustrated",
    "lonely": "lonely", "alone": "lonely", "isolated": "lonely",
    "tired": "tired", "exhausted": "tired", "drained": "tired", "burnt out": "tired",
    "bored": "bored", "boring": "bored",
    "confused": "confused", "lost": "confused", "uncertain": "confused",
    "overwhelmed": "overwhelmed",
    "fear": "fear", "afraid": "fear", "scared": "fear",
}
# Longest cues first so "good day" beats "good" and "burnt out" beats "out".
_EMOTION_ORDERED = sorted(EMOTION_CUES.items(), key=lambda kv: -len(kv[0]))

# --- Importance lexicons ----------------------------------------------------
_ACHIEVEMENT = re.compile(
    r"\b(finished|completed|won|achieved|built|shipped|launched|cracked|solved|"
    r"first time|milestone|breakthrough|nailed|aced)\b", re.IGNORECASE)
_STRUGGLE = re.compile(
    r"\b(failed|lost|argued|fight|fought|broke|stuck|gave up|missed|rejected|"
    r"mistake|regret|terrible|worst)\b", re.IGNORECASE)
_WEIGHTY = re.compile(
    r"\b(important|big|major|huge|life ?changing|never|always|finally|decided)\b",
    re.IGNORECASE)

# --- People extraction ------------------------------------------------------
_NAME = r"[A-Z][a-z]+"
# An interaction cue, then optional filler ("my friend", "the", "cousin"), then
# the capitalised name — so "argued with my friend Rahul" still yields Rahul.
_REL = r"(?:friend|buddy|mate|colleague|classmate|cousin|brother|sister|gf|bf|partner)"
_FILLER = r"(?:my\s+|the\s+|a\s+|" + _REL + r"\s+){0,2}"
_PEOPLE_PRECEDE = re.compile(
    r"\b(?:with|met|meeting|saw|called|texted|messaged|argued with|talked to|"
    r"spoke to|thanks to|helped by|alongside|" + _REL + r")\s+" + _FILLER
    + r"(" + _NAME + r")\b")
_PEOPLE_FOLLOW = re.compile(
    r"\b(" + _NAME + r")\s+(?:helped|called|texted|messaged|told|asked|invited|"
    r"joined|said|gave|came|visited)\b")
# Capitalised words that are never people (so we don't mint junk person entities).
_NOT_NAMES = {
    "I", "Today", "Yesterday", "Tomorrow", "Monday", "Tuesday", "Wednesday",
    "Thursday", "Friday", "Saturday", "Sunday", "January", "February", "March",
    "April", "May", "June", "July", "August", "September", "October", "November",
    "December", "God", "The", "This", "That", "We", "My", "He", "She", "They",
    "It", "Then", "After", "Before", "Also", "Started", "Went", "Worked",
}


def detect_emotion(text: str) -> str | None:
    """First emotion cue found in the text → canonical label (or None)."""
    low = text.lower()
    for cue, label in _EMOTION_ORDERED:
        if cue in low:
            return label
    return None


def detect_category(text: str) -> str:
    """Best-matching life-domain category for a sentence (defaults to 'Life')."""
    best, best_score = "Life", 0
    for cat in _CATEGORY_ORDER:
        n = len(_CATEGORY_RX[cat].findall(text))
        if n > best_score:
            best, best_score = cat, n
    return best


def detect_people(text: str) -> list[str]:
    """Conservative proper-name extraction around interaction cues."""
    found: list[str] = []
    seen: set[str] = set()
    for rx in (_PEOPLE_PRECEDE, _PEOPLE_FOLLOW):
        for m in rx.finditer(text):
            name = m.group(1)
            if name in _NOT_NAMES or name.lower() in seen:
                continue
            seen.add(name.lower())
            found.append(name)
    return found


def _importance(sentence: str, emotion: str | None, has_people: bool) -> float:
    score = 0.45
    if _ACHIEVEMENT.search(sentence):
        score += 0.25
    if _STRUGGLE.search(sentence):
        score += 0.2
    if _WEIGHTY.search(sentence):
        score += 0.1
    score += min(0.2, abs(valence(emotion or "")) * 0.25)
    if has_people:
        score += 0.05
    return round(max(0.3, min(0.95, score)), 3)


@dataclass
class JournalEvent:
    category: str
    description: str
    emotion: str | None
    people: list[str] = field(default_factory=list)
    importance: float = 0.5


def extract_events(text: str) -> list[JournalEvent]:
    """Split a journal entry into structured, categorised events.

    One event per meaningful sentence. Trivial fragments (no category signal and
    fewer than three words) are dropped so the timeline stays clean.
    """
    events: list[JournalEvent] = []
    for raw in _SENTENCE.split(text or ""):
        s = raw.strip().strip("-•* ").strip()
        if not s:
            continue
        category = detect_category(s)
        emotion = detect_emotion(s)
        people = detect_people(s)
        # Drop noise: a too-short fragment with no category, emotion, or person.
        if category == "Life" and not emotion and not people and len(s.split()) < 3:
            continue
        events.append(JournalEvent(
            category=category,
            description=s[:240],
            emotion=emotion,
            people=people,
            importance=_importance(s, emotion, bool(people)),
        ))
    return events


def dominant_emotion(events: list[JournalEvent]) -> str | None:
    """Importance-weighted most-salient emotion across a day's events."""
    weights: dict[str, float] = {}
    for e in events:
        if e.emotion:
            weights[e.emotion] = weights.get(e.emotion, 0.0) + e.importance
    if not weights:
        return None
    return max(weights, key=weights.get)


def summarise_entry(text: str, events: list[JournalEvent]) -> dict:
    """A compact, JSON-serialisable digest of one journal entry."""
    cats = sorted({e.category for e in events})
    people = sorted({p for e in events for p in e.people})
    emo = dominant_emotion(events)
    return {
        "event_count": len(events),
        "categories": cats,
        "people": people,
        "emotion": emo,
        "events": [asdict(e) for e in events],
    }


def _title_from(text: str, day: datetime) -> str:
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    head = (first[:70] + "…") if len(first) > 70 else first
    return f"Journal · {day.date().isoformat()}" + (f" — {head}" if head else "")


# --- DB adapter -------------------------------------------------------------
def add_entry(
    db,
    text: str,
    *,
    ts: datetime | None = None,
    importance: float = 0.6,
    emotion: str | None = None,
    location: dict | None = None,
    title: str | None = None,
    source: str = "journal",
) -> dict:
    """Store a journal entry and wire it into every engine.

    The raw text is preserved as one memory; extracted people/skills/projects/
    goals become entities, and the dominant emotion is tagged so the Emotional
    Cortex, Social Cortex, Habit/Knowledge engines, goal region, and Timeline
    all learn from it automatically.
    """
    from sqlalchemy import select
    from .extract_life import extract_all
    from .ingestion.extract import extract_skills
    from .ingestion.text_ingest import detect_goals
    from .memory_engine import EntityRef, MemoryInput, ingest
    from .models import Entity

    text = (text or "").strip()
    if not text:
        return {"ok": False, "message": "Empty entry — nothing to journal."}

    ts = ts or datetime.now(timezone.utc)
    events = extract_events(text)
    digest = summarise_entry(text, events)
    emotion_final = emotion or digest["emotion"]

    entities: list[EntityRef] = []
    for p in digest["people"]:
        entities.append(EntityRef("person", p, role="involved"))

    skills = extract_skills(text)
    entities += [EntityRef("skill", s, role="practiced") for s in skills]

    low = text.lower()
    project_names = db.execute(
        select(Entity.name).where(Entity.type == "project")
    ).scalars().all()
    linked_projects = [p for p in project_names if p and p.lower() in low]
    entities += [EntityRef("project", p, role="worked_on") for p in linked_projects]

    goals = detect_goals(text)
    entities += [EntityRef("goal", g, role="stated") for g in goals]

    life = extract_all(text, ts.date())
    family_people = {f["person"] for f in life.get("family", []) if f.get("person")}
    entities += [EntityRef("person", p, role="family") for p in sorted(family_people)]

    meta = {"ingest": "journal", "journal": digest}
    meta.update(life)

    memory = ingest(
        db,
        MemoryInput(
            ts=ts, source=source, title=title or _title_from(text, ts),
            content=text, importance=importance, emotion=emotion_final,
            location=location, entities=entities, meta=meta,
        ),
    )
    return {
        "ok": True,
        "memory_id": str(memory.id) if memory else None,
        "date": ts.date().isoformat(),
        "events": digest["events"],
        "categories": digest["categories"],
        "people": digest["people"],
        "skills_linked": skills,
        "projects_linked": linked_projects,
        "goals_detected": goals,
        "emotion": emotion_final,
    }


def _entries_in_window(db, since: datetime, until: datetime | None = None):
    from sqlalchemy import select
    from .models import Memory

    stmt = select(Memory).where(Memory.source == "journal", Memory.ts >= since)
    if until is not None:
        stmt = stmt.where(Memory.ts < until)
    return db.execute(stmt.order_by(Memory.ts.desc())).scalars().all()


def timeline(db, days: int = 30) -> dict:
    """Recent journal entries grouped by day (newest first)."""
    from datetime import timedelta
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = _entries_in_window(db, since)
    by_day: dict[str, list[dict]] = {}
    for m in rows:
        d = m.ts.date().isoformat()
        digest = (m.meta or {}).get("journal", {})
        by_day.setdefault(d, []).append({
            "id": str(m.id),
            "title": m.title,
            "emotion": m.emotion,
            "importance": m.importance,
            "categories": digest.get("categories", []),
            "people": digest.get("people", []),
            "event_count": digest.get("event_count", 0),
        })
    days_out = [{"date": d, "entries": by_day[d]} for d in sorted(by_day, reverse=True)]
    return {
        "ready": bool(days_out),
        "window_days": days,
        "entry_count": len(rows),
        "days": days_out,
    }


def get_day(db, day: str) -> dict:
    """All journal entries (with their extracted events) for one YYYY-MM-DD."""
    from datetime import date, timedelta
    try:
        d = date.fromisoformat(day)
    except ValueError:
        return {"ready": False, "message": "Use a YYYY-MM-DD date."}
    start = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    rows = _entries_in_window(db, start, start + timedelta(days=1))
    entries = [{
        "id": str(m.id),
        "title": m.title,
        "content": m.content,
        "emotion": m.emotion,
        "importance": m.importance,
        "journal": (m.meta or {}).get("journal", {}),
    } for m in rows]
    return {"ready": bool(entries), "date": day, "entries": entries}
