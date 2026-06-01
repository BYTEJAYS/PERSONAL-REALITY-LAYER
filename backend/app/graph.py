"""Neo4j Life Graph projection.

Memories and entities live canonically in Postgres; here we mirror entities and
their co-occurrence relationships into Neo4j so the Life Graph frontend can do
real graph traversal ("what is connected to TGIE?"). Graph writes are best
effort: if Neo4j is unreachable the engine keeps working on Postgres alone.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager

from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from .config import get_settings

log = logging.getLogger("prl.graph")
settings = get_settings()

_driver = None


def _get_driver():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
        )
    return _driver


@contextmanager
def _session():
    yield _get_driver().session()


def ping() -> bool:
    if not settings.neo4j_enabled:
        return False
    try:
        with _session() as s:
            s.run("RETURN 1").consume()
        return True
    except (ServiceUnavailable, Neo4jError, OSError):
        return False


def ensure_constraints() -> None:
    if not settings.neo4j_enabled:
        return
    try:
        with _session() as s:
            s.run(
                "CREATE CONSTRAINT entity_key IF NOT EXISTS "
                "FOR (e:Entity) REQUIRE (e.type, e.name) IS UNIQUE"
            ).consume()
    except (ServiceUnavailable, Neo4jError, OSError) as exc:
        log.warning("Neo4j constraint setup skipped: %s", exc)


def upsert_memory(memory_id: str, title: str, ts: str, entities: list[dict]) -> None:
    """Create the memory node, its entities, and the edges between them.

    `entities` items: {"type", "name", "role"}. Entities that co-occur in the
    same memory are linked with a weighted RELATED edge — the backbone of the
    Life Graph.
    """
    if not settings.neo4j_enabled:
        return
    try:
        with _session() as s:
            s.execute_write(_tx_upsert, memory_id, title, ts, entities)
    except (ServiceUnavailable, Neo4jError, OSError) as exc:
        log.warning("Neo4j write skipped for memory %s: %s", memory_id, exc)


def _tx_upsert(tx, memory_id, title, ts, entities):
    tx.run(
        "MERGE (m:Memory {id: $id}) SET m.title = $title, m.ts = $ts",
        id=memory_id, title=title, ts=ts,
    )
    for e in entities:
        tx.run(
            """
            MERGE (x:Entity {type: $type, name: $name})
            ON CREATE SET x.weight = 1
            ON MATCH SET x.weight = coalesce(x.weight, 0) + 1
            WITH x
            MATCH (m:Memory {id: $mid})
            MERGE (m)-[:INVOLVES {role: $role}]->(x)
            """,
            type=e["type"], name=e["name"], role=e.get("role", "mentions"), mid=memory_id,
        )
    # Co-occurrence edges between every pair of entities in this memory.
    for i in range(len(entities)):
        for j in range(i + 1, len(entities)):
            a, b = entities[i], entities[j]
            tx.run(
                """
                MATCH (x:Entity {type: $ta, name: $na})
                MATCH (y:Entity {type: $tb, name: $nb})
                MERGE (x)-[r:RELATED]-(y)
                ON CREATE SET r.weight = 1
                ON MATCH SET r.weight = r.weight + 1
                """,
                ta=a["type"], na=a["name"], tb=b["type"], nb=b["name"],
            )


def neighborhood(entity_type: str, name: str, limit: int = 50) -> dict:
    """Nodes/edges around one entity — feeds the brain fly-through highlight."""
    if not settings.neo4j_enabled:
        return {"nodes": [], "edges": []}
    try:
        with _session() as s:
            rec = s.run(
                """
                MATCH (c:Entity {type: $type, name: $name})
                OPTIONAL MATCH (c)-[r:RELATED]-(n:Entity)
                WITH c, r, n ORDER BY r.weight DESC LIMIT $limit
                RETURN c AS center, collect(DISTINCT n) AS nbrs,
                       collect(DISTINCT {a: c.name, b: n.name, w: r.weight}) AS rels
                """,
                type=entity_type, name=name, limit=limit,
            ).single()
            if not rec:
                return {"nodes": [], "edges": []}
            nodes = [{"type": rec["center"]["type"], "name": rec["center"]["name"]}]
            nodes += [
                {"type": n["type"], "name": n["name"]} for n in rec["nbrs"] if n is not None
            ]
            edges = [e for e in rec["rels"] if e["b"] is not None]
            return {"nodes": nodes, "edges": edges}
    except (ServiceUnavailable, Neo4jError, OSError) as exc:
        log.warning("Neo4j neighborhood query failed: %s", exc)
        return {"nodes": [], "edges": []}
