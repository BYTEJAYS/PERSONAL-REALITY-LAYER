"""Git connector.

Reads a local repository's history via `git log` and turns each commit into a
Memory. This is the seed data source: real commits, no API key. Author -> person
entity, repo -> project entity, detected tech -> skill entities.
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..memory_engine import EntityRef, MemoryInput, ingest_many
from .extract import extract_skills

# Unit-separated fields, record-separated rows — robust against commit-body newlines.
_FMT = "%H%x1f%an%x1f%ae%x1f%aI%x1f%s%x1f%b%x1e"


def _run_git_log(path: str, limit: int) -> str:
    return subprocess.run(
        ["git", "-C", path, "log", f"--max-count={limit}", f"--pretty=format:{_FMT}", "--no-merges"],
        capture_output=True, text=True, check=True,
    ).stdout


def _parse(raw: str) -> list[dict]:
    commits = []
    for record in raw.split("\x1e"):
        record = record.strip("\n")
        if not record:
            continue
        parts = record.split("\x1f")
        if len(parts) < 6:
            continue
        sha, an, ae, aiso, subject, body = parts[:6]
        commits.append({
            "sha": sha, "author": an, "email": ae, "date": aiso,
            "subject": subject, "body": body,
        })
    return commits


def _importance(subject: str, body: str) -> float:
    text = f"{subject} {body}".lower()
    score = 0.4
    if any(k in text for k in ("feat", "add", "implement", "release", "launch")):
        score += 0.2
    if any(k in text for k in ("fix", "bug", "hotfix", "security")):
        score += 0.1
    if len(body) > 200:
        score += 0.1
    return min(score, 1.0)


def ingest_repo(
    db: Session,
    path: str,
    project: str | None = None,
    limit: int = 500,
    author_filter: str | None = None,
) -> dict:
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isdir(os.path.join(path, ".git")):
        raise ValueError(f"Not a git repository: {path}")

    project_name = project or os.path.basename(path.rstrip("/"))
    commits = _parse(_run_git_log(path, limit))

    items: list[MemoryInput] = []
    for c in commits:
        if author_filter and author_filter.lower() not in (c["author"] + c["email"]).lower():
            continue
        try:
            ts = datetime.fromisoformat(c["date"])
        except ValueError:
            ts = datetime.now(timezone.utc)

        text = f"{c['subject']}\n{c['body']}"
        entities = [
            EntityRef("project", project_name, role="worked_on"),
            EntityRef("person", c["author"], role="authored_by"),
        ]
        entities += [EntityRef("skill", s, role="applied") for s in extract_skills(text)]

        items.append(MemoryInput(
            ts=ts,
            source="git",
            title=c["subject"][:512] or "(empty commit message)",
            content=c["body"].strip(),
            importance=_importance(c["subject"], c["body"]),
            entities=entities,
            meta={"project": project_name, "author": c["author"], "sha": c["sha"]},
            dedupe_key=c["sha"],
        ))

    result = ingest_many(db, items)
    result["project"] = project_name
    result["scanned"] = len(commits)
    return result
