"""Seed the Memory Engine from your local git repositories.

Run on the host (so it can read your repos) against the dockerised Postgres:

    cd prl/backend
    DATABASE_URL=postgresql+psycopg://prl:prl@localhost:5433/prl \
      NEO4J_URI=bolt://localhost:7687 \
      python -m scripts.seed_from_repos ~/transaction-graph-intelligence ~/synthetic-genesis

If no paths are given it scans the home directory for git repos.
"""

from __future__ import annotations

import os
import sys

# Allow `python scripts/seed_from_repos.py` as well as `-m scripts.seed_from_repos`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal, init_db  # noqa: E402
from app.ingestion.git_ingest import ingest_repo  # noqa: E402


def discover_repos(root: str) -> list[str]:
    repos = []
    for name in sorted(os.listdir(root)):
        p = os.path.join(root, name)
        if os.path.isdir(os.path.join(p, ".git")):
            repos.append(p)
    return repos


def main(argv: list[str]) -> None:
    paths = argv or discover_repos(os.path.expanduser("~"))
    if not paths:
        print("No git repositories found.")
        return

    init_db()
    db = SessionLocal()
    try:
        for path in paths:
            try:
                result = ingest_repo(db, path, limit=1000)
                print(
                    f"[{result['project']:<32}] "
                    f"scanned={result['scanned']:>4} "
                    f"created={result['created']:>4} skipped={result['skipped']:>4}"
                )
            except Exception as exc:  # keep going across repos
                print(f"[{os.path.basename(path):<32}] ERROR: {exc}")
    finally:
        db.close()


if __name__ == "__main__":
    main(sys.argv[1:])
