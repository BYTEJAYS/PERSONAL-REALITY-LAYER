"""Connector contract + the normalized record every source emits."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RawEntity:
    type: str  # person | project | goal | skill | place | concept
    name: str
    role: str = "mentions"


@dataclass
class RawMemory:
    """Source-agnostic memory. Adapted to the DB `MemoryInput` server-side, or
    consumed directly by the offline trainer."""
    ts: datetime
    source: str
    title: str
    content: str = ""
    importance: float = 0.4
    memory_type: str | None = None
    entities: list[RawEntity] = field(default_factory=list)
    location: dict | None = None
    meta: dict = field(default_factory=dict)
    dedupe_key: str | None = None


class Connector(ABC):
    name: str = ""
    source: str = ""
    description: str = ""
    sensitive: bool = False  # reads private data (browser history, etc.)

    @abstractmethod
    def available(self) -> bool:
        """True if this source can be read on this machine right now."""

    @abstractmethod
    def fetch(self, **opts) -> Iterator[RawMemory]:
        """Yield normalized memories from the source."""

    def info(self) -> dict:
        return {"name": self.name, "source": self.source,
                "description": self.description, "sensitive": self.sensitive,
                "available": self.available()}
