"""Offline cognitive-model trainer.

Runs the full PCME pipeline WITHOUT any infrastructure (no Postgres/Docker):
reads your local git repositories, builds memories, and computes the cognitive
twin — traits, knowledge distribution, discovered patterns, trends, insights —
straight from your real coding history. Writes `artifacts/cognitive_twin.json`
and prints a readable report.

    cd backend && python scripts/train.py            # scans ~ for git repos
    cd backend && python scripts/train.py ~/repo-a ~/repo-b

Uses commit-local time (so "night owl" reflects your actual clock).
"""

from __future__ import annotations

import importlib.util
import json
import math
import os
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, os.pardir, "app")
sys.path.insert(0, os.path.join(HERE, os.pardir))  # backend/ on path → import app.connectors


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# extract.py is pure-stdlib; load it directly without importing the app package.
extract = _load("extract", os.path.join(APP, "ingestion", "extract.py"))

GIT_FMT = "%H%x1f%an%x1f%ae%x1f%aI%x1f%s%x1f%b%x1e"


# --- ingestion --------------------------------------------------------------
def discover_repos(root: str) -> list[str]:
    out = []
    try:
        for name in sorted(os.listdir(root)):
            p = os.path.join(root, name)
            if os.path.isdir(os.path.join(p, ".git")):
                out.append(p)
    except OSError:
        pass
    return out


def git_commits(path: str, limit: int = 2000) -> list[dict]:
    try:
        raw = subprocess.run(
            ["git", "-C", path, "log", f"--max-count={limit}",
             f"--pretty=format:{GIT_FMT}", "--no-merges"],
            capture_output=True, text=True, check=True,
        ).stdout
    except subprocess.CalledProcessError:
        return []
    commits = []
    for rec in raw.split("\x1e"):
        rec = rec.strip("\n")
        if not rec:
            continue
        parts = rec.split("\x1f")
        if len(parts) < 6:
            continue
        commits.append(dict(sha=parts[0], author=parts[1], email=parts[2],
                            date=parts[3], subject=parts[4], body=parts[5]))
    return commits


def importance(subject: str, body: str) -> float:
    t = f"{subject} {body}".lower()
    s = 0.4
    if any(k in t for k in ("feat", "add", "implement", "release", "launch")):
        s += 0.2
    if any(k in t for k in ("fix", "bug", "hotfix", "security")):
        s += 0.1
    if len(body) > 200:
        s += 0.1
    return min(s, 1.0)


def classify_type(persons: int, has_project: bool, has_skill: bool) -> str:
    if persons >= 2:
        return "social"
    if has_project:
        return "episodic"
    if has_skill:
        return "knowledge"
    return "episodic"


def _raw_to_dict(rm) -> dict:
    skills = [e.name for e in rm.entities if e.type == "skill"]
    project = next((e.name for e in rm.entities if e.type == "project"), rm.source)
    author = next((e.name for e in rm.entities if e.type == "person"), "self")
    return {"ts": rm.ts, "project": project, "author": author, "skills": skills,
            "importance": rm.importance, "title": rm.title,
            "memory_type": rm.memory_type or "episodic", "source": rm.source}


def collect(sources=("git",), repos=None, browser_limit=40000) -> list[dict]:
    """Pull normalized memories from any registered connectors."""
    from app.connectors import registry
    mems: list[dict] = []
    for name in sources:
        c = registry.get(name)
        if not c:
            print(f"   · {name}: unknown connector")
            continue
        if not c.available():
            print(f"   · {name}: unavailable on this machine, skipped")
            continue
        opts: dict = {}
        if name == "git":
            opts["paths"] = repos
        if name == "browser":
            opts["limit"] = browser_limit
        n0 = len(mems)
        for rm in c.fetch(**opts):
            mems.append(_raw_to_dict(rm))
        print(f"   · {name}: +{len(mems) - n0} memories")
    mems.sort(key=lambda m: m["ts"])
    return mems


def build_memories(repos: list[str] | None) -> list[dict]:
    return collect(("git",), repos)


# --- stats helpers ----------------------------------------------------------
def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return 0.0, n
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    sxx = sum((a - mx) ** 2 for a in xs)
    syy = sum((b - my) ** 2 for b in ys)
    if sxx == 0 or syy == 0:
        return 0.0, n
    return sxy / math.sqrt(sxx * syy), n


def conf(n, scale, base=0.35, cap=0.92):
    return round(min(cap, base + n / scale), 2)


def norm(x, full):
    return round(min(1.0, x / full), 3)


def _now(tzinfo):
    return datetime.now(tzinfo or timezone.utc)


# --- model ------------------------------------------------------------------
def knowledge_distribution(mems):
    agg = defaultdict(lambda: {"weight": 0.0, "mentions": 0, "first": None, "last": None})
    for m in mems:
        for s in m["skills"]:
            a = agg[s]
            a["weight"] += m["importance"]
            a["mentions"] += 1
            a["first"] = m["ts"] if a["first"] is None else min(a["first"], m["ts"])
            a["last"] = m["ts"] if a["last"] is None else max(a["last"], m["ts"])
    rows = sorted(agg.items(), key=lambda kv: kv[1]["weight"], reverse=True)
    return [{"skill": k, "weight": round(v["weight"], 2), "mentions": v["mentions"],
             "last_seen": v["last"].date().isoformat()} for k, v in rows]


def project_stats(mems):
    p = defaultdict(lambda: {"n": 0, "first": None, "last": None, "authors": set()})
    for m in mems:
        a = p[m["project"]]
        a["n"] += 1
        a["authors"].add(m["author"])
        a["first"] = m["ts"] if a["first"] is None else min(a["first"], m["ts"])
        a["last"] = m["ts"] if a["last"] is None else max(a["last"], m["ts"])
    return p


def traits(mems, now):
    out = []
    skills = knowledge_distribution(mems)
    projs = project_stats(mems)

    # learning style
    skill_links = sum(len(m["skills"]) for m in mems)
    in_proj = sum(len(m["skills"]) for m in mems if m["project"])
    if skill_links >= 5:
        frac = in_proj / skill_links
        label = "Hands-on builder" if frac >= 0.6 else "Balanced learner" if frac >= 0.4 else "Reader/theorist"
        out.append({"name": "learning_style", "label": label, "score": round(frac, 3),
                    "confidence": conf(skill_links, 50),
                    "explanation": f"{round(frac*100)}% of skill activity happens inside real projects."})

    # persistence
    spans = [(v["last"] - v["first"]).days for v in projs.values() if v["n"] >= 2]
    if spans:
        avg = sum(spans) / len(spans)
        neglected = sum(1 for v in projs.values() if (now - v["last"]).days > 21)
        score = round(norm(avg, 90) * (1 - 0.6 * neglected / len(projs)), 3)
        label = "Highly persistent" if score >= 0.6 else "Moderately persistent" if score >= 0.3 else "Exploratory"
        out.append({"name": "persistence", "label": label, "score": score,
                    "confidence": conf(len(projs), 12),
                    "explanation": f"Projects span {round(avg)} days avg; {neglected}/{len(projs)} gone quiet 3+ wks."})

    # collaboration
    collab = sum(1 for v in projs.values() if len(v["authors"]) >= 2)
    if len(projs) >= 2:
        frac = collab / len(projs)
        label = "Collaborative" if frac >= 0.5 else "Mixed" if frac >= 0.25 else "Independent"
        out.append({"name": "collaboration_preference", "label": label, "score": round(frac, 3),
                    "confidence": conf(len(projs), 12),
                    "explanation": f"{collab}/{len(projs)} projects have multiple contributors."})

    # curiosity
    if len(skills) >= 3:
        new = sum(1 for s in skills
                  if (now - max(m["ts"] for m in mems if s["skill"] in m["skills"])).days <= 9999
                  and any(s["skill"] in m["skills"] and (now - m["ts"]).days <= 60 for m in mems))
        score = round(0.6 * norm(len(skills), 15) + 0.4 * norm(new, 5), 3)
        label = "Highly curious" if score >= 0.6 else "Curious" if score >= 0.35 else "Focused/narrow"
        out.append({"name": "curiosity", "label": label, "score": score,
                    "confidence": conf(len(skills), 20),
                    "explanation": f"{len(skills)} distinct skills, {new} active in the last 60 days."})

    # focus
    if projs:
        total = sum(v["n"] for v in projs.values())
        top = max(v["n"] for v in projs.values())
        share = top / total
        label = "Deep focuser" if share >= 0.5 else "Balanced" if share >= 0.3 else "Multitasker"
        out.append({"name": "focus_concentration", "label": label, "score": round(share, 3),
                    "confidence": conf(total, 40),
                    "explanation": f"Top project holds {round(share*100)}% of all activity."})

    # attention rhythm (commit-local hour)
    hours = [m["ts"].hour for m in mems]
    if len(hours) >= 8:
        hist = Counter(hours)
        h = hist.most_common(1)[0][0]
        label = ("Night owl" if h >= 21 or h < 5 else "Early bird" if h < 11
                 else "Afternoon" if h < 17 else "Evening")
        out.append({"name": "attention_rhythm", "label": label, "score": round(h / 24, 3),
                    "confidence": conf(len(hours), 60),
                    "explanation": f"Activity concentrates around {h:02d}:00 (your local time)."})
    return out


def daily_features(mems):
    frame = defaultdict(lambda: dict(activity=0.0, productivity=0.0, learning=0.0,
                                     building=0.0, late_share=0.0, new_skills=0.0))
    late = defaultdict(int)
    seen = {}
    for m in mems:
        for s in m["skills"]:
            d = m["ts"].date()
            if s not in seen or d < seen[s]:
                seen[s] = d
    for m in mems:
        d = m["ts"].date()
        f = frame[d]
        f["activity"] += 1
        f["productivity"] += m["importance"]
        if m["skills"]:
            f["learning"] += 1
            if m["project"]:
                f["building"] += 1
        late[d] += 1 if m["ts"].hour >= 21 else 0
    for s, d in seen.items():
        if d in frame:
            frame[d]["new_skills"] += 1
    for d, f in frame.items():
        f["late_share"] = late[d] / f["activity"] if f["activity"] else 0.0
    return frame


def patterns(mems):
    frame = daily_features(mems)
    days = sorted(frame)
    found = []
    keys = ["activity", "productivity", "learning", "building", "late_share", "new_skills"]
    if len(days) >= 10:
        from itertools import combinations
        for a, b in combinations(keys, 2):
            xs = [frame[d][a] for d in days]
            ys = [frame[d][b] for d in days]
            if len(set(xs)) < 3 or len(set(ys)) < 3:
                continue
            r, n = pearson(xs, ys)
            if abs(r) >= 0.35:
                found.append({"kind": "correlation", "a": a, "b": b, "r": round(r, 2),
                              "statement": f"On days with more {a}, you tend to do "
                              f"{'more' if r > 0 else 'less'} {b}.", "n": n})
    # peak window
    weight = [0.0] * 24
    for m in mems:
        weight[m["ts"].hour] += m["importance"]
    total = sum(weight)
    if total and len(mems) >= 15:
        best, bs = 0.0, 0
        for s in range(24):
            share = sum(weight[(s + k) % 24] for k in range(4)) / total
            if share > best:
                best, bs = share, s
        if best >= 0.30:
            found.append({"kind": "peak_window", "window": [bs, (bs + 4) % 24],
                          "share": round(best, 2),
                          "statement": f"Your productivity peaks between {bs:02d}:00 and {(bs+4)%24:02d}:00."})
    return found


def trends(mems, now):
    def window(d_from, d_to):
        c = Counter()
        for m in mems:
            age = (now - m["ts"]).days
            if d_to <= age < d_from:
                for s in m["skills"]:
                    c[s] += 1
        return c
    recent, prior = window(30, 0), window(60, 30)
    rising = [{"skill": s, "recent": recent[s], "prior": prior.get(s, 0)}
              for s in recent if recent[s] > prior.get(s, 0)]
    rising.sort(key=lambda x: x["recent"] - x["prior"], reverse=True)
    return {"rising": rising[:6]}


def main(argv):
    sources = ["git"]
    repos: list[str] = []
    for a in argv:
        if a.startswith("--sources="):
            sources = [s.strip() for s in a.split("=", 1)[1].split(",") if s.strip()]
        else:
            repos.append(a)

    print(f"\n⟳ Training cognitive model — sources: {', '.join(sources)}\n")
    mems = collect(sources, repos or None)
    if not mems:
        print("\nNo memories collected from the chosen sources.")
        return
    tz = mems[-1]["ts"].tzinfo
    now = _now(tz)

    by_type = Counter(m["memory_type"] for m in mems)
    model = {
        "trained_at": _now(timezone.utc).isoformat(),
        "profile": {
            "memories": len(mems),
            "repositories": len(repos),
            "span_days": (mems[-1]["ts"] - mems[0]["ts"]).days,
            "first": mems[0]["ts"].date().isoformat(),
            "last": mems[-1]["ts"].date().isoformat(),
        },
        "memory_types": dict(by_type),
        "traits": traits(mems, now),
        "knowledge_distribution": knowledge_distribution(mems)[:12],
        "patterns": patterns(mems),
        "trends": trends(mems, now),
    }

    art_dir = os.path.join(HERE, os.pardir, "artifacts")
    os.makedirs(art_dir, exist_ok=True)
    out_path = os.path.join(art_dir, "cognitive_twin.json")
    with open(out_path, "w") as fh:
        json.dump(model, fh, indent=2, default=str)

    _report(model)
    print(f"\n✓ Model trained. Artifact → {os.path.relpath(out_path)}\n")


def _report(model):
    p = model["profile"]
    print("═" * 64)
    print("  COGNITIVE TWIN")
    print("═" * 64)
    print(f"  {p['memories']} memories · {p['repositories']} projects · "
          f"{p['span_days']} days ({p['first']} → {p['last']})")
    print(f"  memory types: " + ", ".join(f"{k} {v}" for k, v in model["memory_types"].items()))

    print("\n  TRAITS")
    for t in model["traits"]:
        print(f"    • {t['name']:<24} {t['label']:<22} "
              f"(score {t['score']}, conf {t['confidence']})")
        print(f"        {t['explanation']}")

    print("\n  KNOWLEDGE DISTRIBUTION")
    for k in model["knowledge_distribution"][:8]:
        bar = "█" * max(1, int(k["weight"]))
        print(f"    {k['skill']:<20} {bar} {k['weight']}")

    if model["patterns"]:
        print("\n  DISCOVERED PATTERNS")
        for pat in model["patterns"]:
            print(f"    • {pat['statement']}")

    if model["trends"]["rising"]:
        print("\n  RISING INTERESTS")
        for r in model["trends"]["rising"]:
            print(f"    ↑ {r['skill']} ({r['prior']} → {r['recent']})")


if __name__ == "__main__":
    main(sys.argv[1:])
