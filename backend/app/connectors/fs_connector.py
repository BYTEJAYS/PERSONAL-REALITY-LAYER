"""Filesystem connector — documents become memories (by modified time)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import datetime, timezone

from ..ingestion.extract import extract_skills
from .base import Connector, RawEntity, RawMemory

_DEFAULT_ROOTS = ["~/Documents", "~/Downloads", "~/Desktop"]
_EXTS = {".pdf", ".md", ".txt", ".doc", ".docx", ".epub", ".ipynb", ".key", ".pptx"}
_SKIP_DIRS = {"node_modules", ".git", "Library", "venv", ".venv", "__pycache__"}


class FilesystemConnector(Connector):
    name = "files"
    source = "files"
    description = "Documents in Documents/Downloads/Desktop — by modified time."
    sensitive = True

    def available(self) -> bool:
        return any(os.path.isdir(os.path.expanduser(r)) for r in _DEFAULT_ROOTS)

    def fetch(self, roots: list[str] | None = None, limit: int = 5000, **_) -> Iterator[RawMemory]:
        roots = [os.path.expanduser(r) for r in (roots or _DEFAULT_ROOTS)]
        seen = 0
        for root in roots:
            if not os.path.isdir(root):
                continue
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
                for fn in filenames:
                    if seen >= limit:
                        return
                    ext = os.path.splitext(fn)[1].lower()
                    if ext not in _EXTS:
                        continue
                    path = os.path.join(dirpath, fn)
                    try:
                        mtime = os.path.getmtime(path)
                    except OSError:
                        continue
                    ts = datetime.fromtimestamp(mtime, tz=timezone.utc).astimezone()
                    stem = os.path.splitext(fn)[0]
                    ents = [RawEntity("skill", s, "studied") for s in extract_skills(stem)]
                    yield RawMemory(
                        ts=ts, source="files", title=fn[:300], content=path,
                        importance=0.3, memory_type="knowledge", entities=ents,
                        meta={"ext": ext}, dedupe_key=f"{path}:{int(mtime)}",
                    )
                    seen += 1
