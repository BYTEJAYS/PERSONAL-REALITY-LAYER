"""Pluggable text embeddings.

The whole point of PRL's memory is *semantic* recall — "what have I been
learning about agents?" should surface memories that never use the word
"agents". That only works if the vector for a piece of text encodes its
*meaning*, not just which tokens it happens to contain.

Providers, in order of fidelity:

- ``sentence_transformers`` (default): a real local transformer encoder
  (all-MiniLM-L6-v2, 384-dim). Runs fully offline once the model is cached, no
  API key, no data leaves the machine. This is what makes recall actually
  semantic.
- ``openai``: hosted embeddings (text-embedding-3-small). Highest quality but
  sends memory text to the provider; opt-in only.
- ``local``: a deterministic feature-hashing embedder. NO semantic structure —
  it only matches on shared tokens. Kept solely as a zero-dependency fallback
  so the system still boots if the model can't load; not for real use.

All providers return an L2-normalised vector of ``settings.embedding_dim``
dimensions so they're interchangeable at the pgvector layer.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
import threading

from .config import get_settings

log = logging.getLogger("prl.embeddings")
settings = get_settings()
_DIM = settings.embedding_dim

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _local_embed(text: str) -> list[float]:
    """Hash tokens into a fixed-dim vector, then L2-normalise.

    Fallback only — this has no notion of meaning (synonyms look unrelated).
    """
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


# --- real local transformer encoder ----------------------------------------
# Loaded once, lazily, behind a lock (the model is a few hundred MB in RAM and
# the first call pays a one-time load cost). Guarded so a load failure degrades
# to the hashing fallback instead of taking the API down.
_st_model = None
_st_lock = threading.Lock()
_st_failed = False


def _get_st_model():
    global _st_model, _st_failed
    if _st_model is not None or _st_failed:
        return _st_model
    with _st_lock:
        if _st_model is None and not _st_failed:
            try:
                from sentence_transformers import SentenceTransformer

                log.info("loading embedding model %s ...", settings.st_model)
                model = SentenceTransformer(settings.st_model)
                got = model.get_sentence_embedding_dimension()
                if got != _DIM:
                    raise ValueError(
                        f"model dim {got} != configured embedding_dim {_DIM}; "
                        "set EMBEDDING_DIM to match or pick a 384-dim model"
                    )
                _st_model = model
                log.info("embedding model ready (dim=%d)", got)
            except Exception as exc:  # noqa: BLE001 — never let this crash the API
                _st_failed = True
                log.error("could not load embedding model (%s); falling back to hashing embedder", exc)
    return _st_model


def _st_embed(text: str) -> list[float]:
    model = _get_st_model()
    if model is None:
        return _local_embed(text)
    vec = model.encode(text, normalize_embeddings=True)
    return vec.astype("float32").tolist()


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
    provider = settings.embedding_provider
    if provider == "openai" and settings.openai_api_key:
        return _openai_embed(text)
    if provider in ("sentence_transformers", "st"):
        return _st_embed(text)
    return _local_embed(text)


def model_name() -> str:
    """Human-readable id of the active embedder (for health/debug)."""
    p = settings.embedding_provider
    if p == "openai" and settings.openai_api_key:
        return "openai:text-embedding-3-small"
    if p in ("sentence_transformers", "st"):
        return f"sentence_transformers:{settings.st_model}" if not _st_failed else "local:hashing(fallback)"
    return "local:hashing"
