"""Lightweight access control for a public companion with a private owner.

One role only: the OWNER token (full access to every endpoint, set via env so it
isn't baked into the repo):

    OWNER_TOKEN=...                 # you — the one code you decide

Everyone else needs NO code: the companion voice (`/companion/*`) is open to all
and applies record redaction, so strangers never reach raw finances/health/
memories. Raw endpoints stay owner-only. Pure helpers are unit-testable; the
FastAPI dependencies wrap them.
"""

from __future__ import annotations

import os

from fastapi import Header, HTTPException


def classify_token(token: str | None, owner: str | None) -> str | None:
    """Return 'owner' if the token is the owner code, else None."""
    if not token:
        return None
    if owner and token == owner:
        return "owner"
    return None


def _env_roles(token: str | None) -> str | None:
    return classify_token(token, os.getenv("OWNER_TOKEN"))


def require_companion(x_access_token: str | None = Header(default=None)) -> str:
    """Open to everyone — the companion voice is public, no code required.

    If the owner code is presented we still recognise it (so /about can report
    the role), but no token is ever required and nobody is turned away."""
    return _env_roles(x_access_token) or "guest"


def require_owner(x_access_token: str | None = Header(default=None)) -> str:
    """Owner-only — use to lock raw endpoints. With no OWNER_TOKEN set the gate
    is open (local/dev convenience)."""
    if not os.getenv("OWNER_TOKEN"):
        return "open"
    if _env_roles(x_access_token) != "owner":
        raise HTTPException(status_code=403, detail="Owner access only.")
    return "owner"
