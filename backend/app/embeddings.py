"""Pluggable text embeddings.

The default `local` provider is a deterministic, offline feature-hashing
embedder: no network, no model download, stable across runs. It is good enough
for semantic-ish nearest-neighbour grouping while the system is small, and the
interface matches a real model so you can swap in OpenAI / sentence-transformers
later without touching callers.
"""

from __future__ import annotations

import hashlib
import math
import re

from .config import get_settings

settings = get_settings()
_DIM = settings.embedding_dim

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _local_embed(text: str) -> list[float]:
    """Hash tokens into a fixed-dim vector, then L2-normalise."""
    vec = [0.0] * _DIM
    for tok in _tokenize(text):
        h = hashlib.blake2b(tok.encode(), digest_size=8).digest()
        idx = int.from_bytes(h[:4], "little") % _DIM
        sign = 1.0 if h[4] & 1 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


def _openai_embed(text: str) -> list[float]:
    import httpx  # imported lazily so the local path needs no extra deps

    resp = httpx.post(
        "https://api.openai.com/v1/embeddings",
        headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        json={"model": "text-embedding-3-small", "input": text, "dimensions": _DIM},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["data"][0]["embedding"]


def embed(text: str) -> list[float]:
    if not text.strip():
        return [0.0] * _DIM
    if settings.embedding_provider == "openai" and settings.openai_api_key:
        return _openai_embed(text)
    return _local_embed(text)
