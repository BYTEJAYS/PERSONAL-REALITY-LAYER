"""Knowledge Evolution Graph (V2).

Reconstructs how ideas emerged and fed into one another over time, e.g.

    Python → FastAPI → Backend → Fraud Detection → ML → Graph Intelligence → PRL

Nodes are concepts (skills / projects) with a first-seen date. A directed edge
A → B means B appeared *after* A and the two co-occur in real memories, so A
plausibly fed into B. Because every edge points forward in time the graph is a
DAG; its longest weighted path is the "spine" of intellectual evolution.

`build_graph()` is pure (concepts + co-occurrence counts in) and unit-testable;
`build(db)` derives both from the Memory store.
"""

from __future__ import annotations

from datetime import datetime, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- pure graph construction ------------------------------------------------
def build_graph(
    concepts: list[dict],
    cooccur: dict[tuple[str, str], int],
    max_predecessors: int = 2,
) -> dict:
    """`concepts`: [{name, first_seen (sortable), weight, mentions}].
    `cooccur`: {(a, b): count} undirected co-occurrence counts."""
    if not concepts:
        return {"nodes": [], "edges": [], "spine": [], "root": None, "leaf": None}

    ordered = sorted(concepts, key=lambda c: (c["first_seen"], c["name"]))
    order = {c["name"]: i for i, c in enumerate(ordered)}
    nodes = [
        {
            "name": c["name"],
            "first_seen": c["first_seen"],
            "order": order[c["name"]],
            "weight": round(float(c.get("weight", 0)), 2),
            "mentions": int(c.get("mentions", 0)),
        }
        for c in ordered
    ]

    # Direct each co-occurring pair from the earlier concept to the later one.
    directed: list[tuple[str, str, int]] = []
    for (a, b), count in cooccur.items():
        if a not in order or b not in order or order[a] == order[b] or count <= 0:
            continue
        src, tgt = (a, b) if order[a] < order[b] else (b, a)
        directed.append((src, tgt, count))

    # Keep only each concept's strongest predecessors → a clean "what led to this".
    by_target: dict[str, list[tuple[str, str, int]]] = {}
    for e in directed:
        by_target.setdefault(e[1], []).append(e)
    edges: list[dict] = []
    for tgt, es in by_target.items():
        es.sort(key=lambda e: e[2], reverse=True)
        for src, _t, w in es[:max_predecessors]:
            edges.append({
                "source": src,
                "target": tgt,
                "strength": w,
                "order_gap": order[tgt] - order[src],
            })

    spine = _longest_path(nodes, edges)
    return {
        "nodes": nodes,
        "edges": edges,
        "spine": spine,
        "root": spine[0] if spine else None,
        "leaf": spine[-1] if spine else None,
    }


def _longest_path(nodes: list[dict], edges: list[dict]) -> list[str]:
    """Longest strength-weighted path through the time-ordered DAG."""
    incoming: dict[str, list[tuple[str, int]]] = {}
    for e in edges:
        incoming.setdefault(e["target"], []).append((e["source"], e["strength"]))

    best: dict[str, float] = {}
    prev: dict[str, str | None] = {}
    end = None
    for n in sorted(nodes, key=lambda n: n["order"]):  # topological order
        name = n["name"]
        b, p = 0.0, None
        for src, w in incoming.get(name, []):
            if best.get(src, 0) + w > b:
                b, p = best[src] + w, src
        best[name], prev[name] = b, p
        if end is None or b > best.get(end, -1):
            end = name

    if end is None or best.get(end, 0) == 0:
        return []
    chain: list[str] = []
    cur: str | None = end
    while cur is not None:
        chain.append(cur)
        cur = prev.get(cur)
    chain.reverse()
    return chain


# --- DB adapter -------------------------------------------------------------
def build(db, min_cooccur: int = 1) -> dict:
    from sqlalchemy import func, select
    from .models import Entity, Memory, MemoryEntity

    now = _now()

    concept_rows = db.execute(
        select(
            Entity.name,
            Entity.weight,
            func.count(MemoryEntity.memory_id).label("mentions"),
            func.min(Memory.ts).label("first_seen"),
        )
        .join(MemoryEntity, MemoryEntity.entity_id == Entity.id)
        .join(Memory, Memory.id == MemoryEntity.memory_id)
        .where(Entity.type.in_(("skill", "project")))
        .group_by(Entity.id)
    ).all()

    if len(concept_rows) < 2:
        return {"generated_at": now.isoformat(), "ready": False,
                "message": "Not enough concepts yet to trace intellectual evolution."}

    concepts = [
        {"name": name, "weight": w, "mentions": n, "first_seen": fs.isoformat()}
        for name, w, n, fs in concept_rows
    ]

    # Co-occurrence: two concepts sharing a memory.
    a = MemoryEntity.__table__.alias("a")
    b = MemoryEntity.__table__.alias("b")
    ea = Entity.__table__.alias("ea")
    eb = Entity.__table__.alias("eb")
    pair_rows = db.execute(
        select(ea.c.name, eb.c.name, func.count().label("c"))
        .select_from(
            a.join(b, (a.c.memory_id == b.c.memory_id) & (a.c.entity_id < b.c.entity_id))
            .join(ea, ea.c.id == a.c.entity_id)
            .join(eb, eb.c.id == b.c.entity_id)
        )
        .where(ea.c.type.in_(("skill", "project")), eb.c.type.in_(("skill", "project")))
        .group_by(ea.c.name, eb.c.name)
    ).all()
    cooccur = {(na, nb): c for na, nb, c in pair_rows if c >= min_cooccur}

    graph = build_graph(concepts, cooccur)
    graph["generated_at"] = now.isoformat()
    graph["ready"] = bool(graph["nodes"])
    graph["node_count"] = len(graph["nodes"])
    graph["edge_count"] = len(graph["edges"])
    return graph
