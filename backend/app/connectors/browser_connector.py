"""Browser connector — Chrome history page-visits become memories.

Reads the local Chrome history SQLite DB (copied to a temp file and opened
read-only/immutable so it works even while Chrome is running). Local-only;
nothing leaves the machine. High-signal: produces real per-day activity.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from collections.abc import Iterator
from datetime import datetime, timezone
from urllib.parse import urlparse

from ..ingestion.extract import extract_skills
from .base import Connector, RawEntity, RawMemory

# Chrome (and Chromium-family) default-profile history locations.
_CANDIDATES = [
    "~/Library/Application Support/Google/Chrome/Default/History",
    "~/Library/Application Support/Google/Chrome/Profile 1/History",
    "~/Library/Application Support/Chromium/Default/History",
    "~/Library/Application Support/BraveSoftware/Brave-Browser/Default/History",
    "~/Library/Application Support/Microsoft Edge/Default/History",
]

# Chrome timestamps: microseconds since 1601-01-01 UTC.
_WEBKIT_EPOCH_OFFSET = 11644473600


def _find_db() -> str | None:
    for c in _CANDIDATES:
        p = os.path.expanduser(c)
        if os.path.exists(p):
            return p
    return None


def _to_dt(webkit_micros: int) -> datetime | None:
    if not webkit_micros:
        return None
    unix = webkit_micros / 1_000_000 - _WEBKIT_EPOCH_OFFSET
    if unix <= 0:
        return None
    return datetime.fromtimestamp(unix, tz=timezone.utc).astimezone()


# Noise domains that aren't meaningful "activity" topics.
_SKIP_DOMAINS = {"newtab", "localhost", "127.0.0.1"}


class BrowserConnector(Connector):
    name = "browser"
    source = "browser"
    description = "Chrome/Chromium history — page visits as memories (local, read-only)."
    sensitive = True

    def available(self) -> bool:
        return _find_db() is not None

    def fetch(self, limit: int = 40000, **_) -> Iterator[RawMemory]:
        src = _find_db()
        if not src:
            return
        tmpdir = tempfile.mkdtemp(prefix="prl_browser_")
        tmp = os.path.join(tmpdir, "History")
        try:
            shutil.copy2(src, tmp)
            conn = sqlite3.connect(f"file:{tmp}?immutable=1", uri=True)
            try:
                rows = conn.execute(
                    """
                    SELECT v.visit_time, u.url, u.title
                    FROM visits v JOIN urls u ON u.id = v.url
                    ORDER BY v.visit_time DESC LIMIT ?
                    """,
                    (limit,),
                )
                for visit_time, url, title in rows:
                    ts = _to_dt(visit_time)
                    if ts is None:
                        continue
                    domain = (urlparse(url).netloc or "").replace("www.", "")
                    if not domain or domain in _SKIP_DOMAINS:
                        continue
                    ents = [RawEntity("place", domain, "visited")]
                    ents += [RawEntity("skill", s, "read_about")
                             for s in extract_skills(title or "")]
                    yield RawMemory(
                        ts=ts, source="browser",
                        title=(title or domain)[:300], content=url[:1000],
                        importance=0.2, memory_type="episodic", entities=ents,
                        meta={"domain": domain}, dedupe_key=f"{visit_time}",
                    )
            finally:
                conn.close()
        except (OSError, sqlite3.Error):
            return
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
