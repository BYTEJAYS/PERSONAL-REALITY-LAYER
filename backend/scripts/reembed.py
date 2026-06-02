"""Recompute every memory's embedding with the currently-configured embedder.

Run this after switching ``embedding_provider`` (e.g. hashing -> sentence
transformers). Existing vectors were produced by the old model and are
meaningless to the new one, so semantic search is broken until they're
recomputed. Idempotent: safe to run repeatedly.

    docker compose exec api python -m scripts.reembed
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.embeddings import embed, model_name  # noqa: E402
from app.models import Memory  # noqa: E402


def main() -> None:
    print(f"Re-embedding with: {model_name()}")
    db = SessionLocal()
    try:
        memories = list(db.execute(select(Memory)).scalars().all())
        total = len(memories)
        print(f"{total} memories to re-embed ...")
        for i, m in enumerate(memories, 1):
            text = f"{m.title}\n{m.content}".strip()
            m.embedding = embed(text)
            if i % 10 == 0 or i == total:
                print(f"  {i}/{total}")
        db.commit()
        print("Done — embeddings rebuilt and committed.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
