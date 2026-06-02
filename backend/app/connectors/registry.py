"""Connector registry — discover and resolve connectors by name."""

from __future__ import annotations

from .base import Connector
from .browser_connector import BrowserConnector
from .fs_connector import FilesystemConnector
from .git_connector import GitConnector
from .shell_connector import ShellConnector

_REGISTRY: dict[str, Connector] = {
    c.name: c for c in (
        GitConnector(),
        BrowserConnector(),
        FilesystemConnector(),
        ShellConnector(),
    )
}


def get(name: str) -> Connector | None:
    return _REGISTRY.get(name)


def all_connectors() -> list[Connector]:
    return list(_REGISTRY.values())


def available_names() -> list[str]:
    return [c.name for c in _REGISTRY.values() if c.available()]
