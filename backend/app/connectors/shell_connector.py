"""Shell-history connector — commands become dev-activity memories.

Requires zsh EXTENDED_HISTORY (entries prefixed `: <epoch>:<dur>;<cmd>`); plain
history has no timestamps and yields nothing (can't place events in time).
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from datetime import datetime, timezone

from .base import Connector, RawEntity, RawMemory

_HISTFILE = "~/.zsh_history"
_LINE = re.compile(r"^: (\d+):\d+;(.*)$")

# Map common CLI tools → skill entities.
_TOOLS = {
    "git": "Git", "python": "Python", "python3": "Python", "pip": "Python",
    "node": "JavaScript", "npm": "JavaScript", "npx": "JavaScript", "yarn": "JavaScript",
    "docker": "Docker", "kubectl": "Docker", "psql": "Databases", "redis-cli": "Databases",
    "curl": "APIs", "ssh": "DevOps", "make": "DevOps",
}


class ShellConnector(Connector):
    name = "shell"
    source = "shell"
    description = "zsh history (needs EXTENDED_HISTORY for timestamps)."
    sensitive = True

    def _path(self) -> str:
        return os.path.expanduser(_HISTFILE)

    def available(self) -> bool:
        p = self._path()
        if not os.path.exists(p):
            return False
        try:
            with open(p, "r", errors="ignore") as fh:
                for _ in range(200):
                    line = fh.readline()
                    if not line:
                        break
                    if _LINE.match(line):
                        return True
        except OSError:
            return False
        return False

    def fetch(self, limit: int = 20000, **_) -> Iterator[RawMemory]:
        p = self._path()
        try:
            with open(p, "r", errors="ignore") as fh:
                lines = fh.readlines()
        except OSError:
            return
        count = 0
        for line in lines:
            m = _LINE.match(line)
            if not m:
                continue
            epoch, cmd = int(m.group(1)), m.group(2).strip()
            if not cmd or count >= limit:
                continue
            ts = datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone()
            tool = cmd.split()[0] if cmd.split() else ""
            ents = []
            if tool in _TOOLS:
                ents.append(RawEntity("skill", _TOOLS[tool], "used"))
            yield RawMemory(
                ts=ts, source="shell", title=cmd[:200], importance=0.15,
                memory_type="episodic", entities=ents,
                meta={"tool": tool}, dedupe_key=f"{epoch}:{hash(cmd) & 0xffffffff}",
            )
            count += 1
