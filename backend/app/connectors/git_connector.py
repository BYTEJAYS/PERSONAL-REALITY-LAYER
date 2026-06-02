"""Git connector — commits become episodic memories."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from datetime import datetime

from ..ingestion.extract import extract_skills
from .base import Connector, RawEntity, RawMemory

_FMT = "%H%x1f%an%x1f%ae%x1f%aI%x1f%s%x1f%b%x1e"


def _importance(subject: str, body: str) -> float:
    t = f"{subject} {body}".lower()
    s = 0.4
    if any(k in t for k in ("feat", "add", "implement", "release", "launch")):
        s += 0.2
    if any(k in t for k in ("fix", "bug", "hotfix", "security")):
        s += 0.1
    if len(body) > 200:
        s += 0.1
    return min(s, 1.0)


def _discover(root: str) -> list[str]:
    out = []
    try:
        for name in sorted(os.listdir(root)):
            p = os.path.join(root, name)
            if os.path.isdir(os.path.join(p, ".git")):
                out.append(p)
    except OSError:
        pass
    return out


class GitConnector(Connector):
    name = "git"
    source = "git"
    description = "Local git repositories — commits as episodic work memories."

    def available(self) -> bool:
        try:
            subprocess.run(["git", "--version"], capture_output=True, check=True)
            return True
        except (OSError, subprocess.CalledProcessError):
            return False

    def fetch(self, paths: list[str] | None = None, limit: int = 2000, **_) -> Iterator[RawMemory]:
        repos = paths or _discover(os.path.expanduser("~"))
        repos = [r for r in repos if os.path.basename(r.rstrip("/")) != "prl"]
        for path in repos:
            project = os.path.basename(path.rstrip("/"))
            try:
                raw = subprocess.run(
                    ["git", "-C", path, "log", f"--max-count={limit}",
                     f"--pretty=format:{_FMT}", "--no-merges"],
                    capture_output=True, text=True, check=True,
                ).stdout
            except subprocess.CalledProcessError:
                continue
            for rec in raw.split("\x1e"):
                rec = rec.strip("\n")
                if not rec:
                    continue
                parts = rec.split("\x1f")
                if len(parts) < 6:
                    continue
                sha, an, _ae, aiso, subject, body = parts[:6]
                try:
                    ts = datetime.fromisoformat(aiso)
                except ValueError:
                    continue
                ents = [RawEntity("project", project, "worked_on"),
                        RawEntity("person", an, "authored_by")]
                ents += [RawEntity("skill", s, "applied")
                         for s in extract_skills(f"{subject}\n{body}")]
                yield RawMemory(
                    ts=ts, source="git", title=subject[:512] or "(empty commit)",
                    content=body.strip(), importance=_importance(subject, body),
                    memory_type="episodic", entities=ents,
                    meta={"project": project, "sha": sha}, dedupe_key=sha,
                )
