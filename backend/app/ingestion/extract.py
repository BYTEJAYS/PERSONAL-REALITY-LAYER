"""Lightweight entity extraction for ingested text.

A keyword/regex pass that pulls skills and concepts out of commit messages,
notes, etc. Deliberately dependency-free; swap in an LLM extractor later behind
the same `extract_skills` signature.
"""

from __future__ import annotations

import re

# Canonical skill name -> regex of surface forms. Order doesn't matter.
SKILL_PATTERNS: dict[str, str] = {
    "Python": r"\bpython|\.py\b|fastapi|pydantic|uvicorn|celery|numpy|pandas",
    "FastAPI": r"\bfastapi\b",
    "TypeScript": r"\btypescript|\.tsx?\b",
    "JavaScript": r"\bjavascript|\.jsx?\b|node\.?js",
    "React": r"\breact\b|next\.?js|r3f|react three fiber",
    "Three.js": r"\bthree\.?js|webgl|r3f|react three fiber",
    "Machine Learning": r"\bml\b|machine learning|model training|inference|embedding",
    "Neural Networks": r"\bneural net|\bnn\b|deep learning|transformer",
    "Fraud Detection": r"\bfraud\b|anomaly detection|aml\b",
    "Graph": r"\bneo4j|graph database|knowledge graph|networkx|cypher",
    "Databases": r"\bpostgres|postgresql|sql\b|redis|sqlite|pgvector",
    "Docker": r"\bdocker|compose|container",
    "Statistics": r"\bstatistics|probability|bayesian|regression",
    "APIs": r"\bapi\b|rest\b|endpoint|websocket",
    "Simulation": r"\bsimulation|simulator|physics engine|agent-based",
}

_COMPILED = {name: re.compile(pat, re.IGNORECASE) for name, pat in SKILL_PATTERNS.items()}


def extract_skills(text: str) -> list[str]:
    return [name for name, rx in _COMPILED.items() if rx.search(text)]
