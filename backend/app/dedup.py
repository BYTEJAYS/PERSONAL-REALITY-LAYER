"""Duplicate Elimination (Memory-Architecture V3).

The vision: 500 near-identical photos should not be 500 full copies — store one
master plus the *differences*. Here, near-duplicate memories are detected by
cosine similarity over their Memory-DNA embeddings, collapsed into a group with a
chosen master, and the redundant members reduced to a difference magnitude
(1 − similarity) rather than a full copy.

The pure core (`find_duplicate_groups`) is unit-testable on plain float vectors;
`build(db)` runs it over the stored embeddings and reports the storage saved.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = na = nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


@dataclass
class DupItem:
    id: str
    vector: list[float]
    importance: float = 0.5
    ts: datetime | None = None
    title: str = ""


@dataclass
class DupGroup:
    master_id: str
    master_title: str
    member_ids: list[str] = field(default_factory=list)   # redundant copies (not the master)
    diffs: list[float] = field(default_factory=list)      # 1 - sim, per member
    avg_similarity: float = 0.0

    @property
    def size(self) -> int:
        return len(self.member_ids) + 1

    def as_dict(self) -> dict:
        return {
            "master_id": self.master_id,
            "master_title": self.master_title,
            "size": self.size,
            "redundant": len(self.member_ids),
            "member_ids": self.member_ids,
            "avg_similarity": round(self.avg_similarity, 4),
            "max_diff": round(max(self.diffs), 4) if self.diffs else 0.0,
        }


def find_duplicate_groups(items: list[DupItem], threshold: float = 0.92) -> list[DupGroup]:
    """Greedily cluster near-duplicates. The master is the most important member
    (ties broken by the earliest timestamp — the original). Each redundant member
    keeps only its difference magnitude to the master."""
    pool = [it for it in items if it.vector]
    used: set[int] = set()
    groups: list[DupGroup] = []

    for i, anchor in enumerate(pool):
        if i in used:
            continue
        cluster = [(i, anchor)]
        for j in range(i + 1, len(pool)):
            if j in used:
                continue
            if cosine(anchor.vector, pool[j].vector) >= threshold:
                cluster.append((j, pool[j]))

        if len(cluster) == 1:
            used.add(i)
            continue

        for idx, _ in cluster:
            used.add(idx)

        # Pick the master: highest importance, then earliest timestamp.
        master_idx, master = max(
            cluster,
            key=lambda pair: (
                pair[1].importance,
                -(pair[1].ts.timestamp() if pair[1].ts else 0.0),
            ),
        )
        diffs, sims = [], []
        member_ids = []
        for idx, it in cluster:
            if idx == master_idx:
                continue
            s = cosine(master.vector, it.vector)
            sims.append(s)
            diffs.append(1.0 - s)
            member_ids.append(it.id)
        groups.append(
            DupGroup(
                master_id=master.id,
                master_title=master.title,
                member_ids=member_ids,
                diffs=diffs,
                avg_similarity=sum(sims) / len(sims) if sims else 0.0,
            )
        )

    groups.sort(key=lambda g: g.size, reverse=True)
    return groups


def dedup_savings(total: int, groups: list[DupGroup]) -> dict:
    """How many full copies the master+diff scheme removes."""
    redundant = sum(len(g.member_ids) for g in groups)
    return {
        "total": total,
        "duplicate_groups": len(groups),
        "redundant_copies": redundant,
        # fraction of memories that collapse into a master/diff instead of a full copy
        "savings_ratio": round(redundant / total, 3) if total else 0.0,
    }


# --- DB adapter -------------------------------------------------------------
def build(db, threshold: float = 0.95, limit: int = 5000) -> dict:
    from sqlalchemy import select
    from .models import Memory

    rows = db.execute(
        select(Memory.id, Memory.title, Memory.importance, Memory.ts, Memory.embedding)
        .where(Memory.embedding.isnot(None))
        .limit(limit)
    ).all()

    items = [
        DupItem(
            id=str(mid),
            vector=list(emb) if emb is not None else [],
            importance=imp if imp is not None else 0.5,
            ts=ts,
            title=title,
        )
        for mid, title, imp, ts, emb in rows
    ]
    groups = find_duplicate_groups(items, threshold=threshold)
    savings = dedup_savings(len(items), groups)
    return {
        "generated_at": _now().isoformat(),
        "ready": len(items) > 0,
        "threshold": threshold,
        **savings,
        "groups": [g.as_dict() for g in groups[:200]],
    }
