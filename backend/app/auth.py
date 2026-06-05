"""Lightweight token access control for a friends-only deployment.

Two roles: the OWNER token (full access to every endpoint) and FRIEND tokens
(only the discreet `/companion/*` voice). Tokens come from env so none are baked
into the repo:

    OWNER_TOKEN=...                 # you
    FRIEND_TOKENS=alice123,bob456   # one per friend (comma-separated)

This is deliberately simple — a real "only my friends" gate, not OAuth. Each
friend gets their own token so you can revoke one without affecting the rest.
Pure helpers are unit-testable; the FastAPI dependencies wrap them.
"""

from __future__ import annotations

import os

from fastapi import Header, HTTPException


def parse_tokens(value: str | None) -> set[str]:
    return {t.strip() for t in (value or "").split(",") if t.strip()}


def classify_token(token: str | None, owner: str | None, friends: set[str]) -> str | None:
    """Return 'owner', 'friend', or None (unauthorised)."""
    if not token:
        return None
    if owner and token == owner:
        return "owner"
    if token in friends:
        return "friend"
    return None


def _env_roles(token: str | None) -> str | None:
    return classify_token(token, os.getenv("OWNER_TOKEN"),
                          parse_tokens(os.getenv("FRIEND_TOKENS")))


def require_companion(x_access_token: str | None = Header(default=None)) -> str:
    """Allow owner OR friend tokens — used to gate the /companion voice."""
    role = _env_roles(x_access_token)
    # If no tokens are configured at all, the gate is open (local/dev convenience).
    if not os.getenv("OWNER_TOKEN") and not os.getenv("FRIEND_TOKENS"):
        return "open"
    if role is None:
        raise HTTPException(status_code=401, detail="A valid access token is required.")
    return role


def require_owner(x_access_token: str | None = Header(default=None)) -> str:
    """Owner-only — use to lock raw endpoints in a friends deployment."""
    if not os.getenv("OWNER_TOKEN"):
        return "open"
    if _env_roles(x_access_token) != "owner":
        raise HTTPException(status_code=403, detail="Owner access only.")
    return "owner"
