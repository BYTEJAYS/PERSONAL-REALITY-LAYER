from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .config import get_settings
from .db import Base

EMBEDDING_DIM = get_settings().embedding_dim


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Entity types map onto the brain's cognitive regions.
ENTITY_TYPES = ("person", "project", "goal", "skill", "place")

REGION_FOR_ENTITY = {
    "person": "social",
    "project": "project",
    "goal": "goal",
    "skill": "knowledge",
    "place": "memory",
}


class Memory(Base):
    """The atomic unit of reality. Every ingested signal becomes one of these."""

    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source: Mapped[str] = mapped_column(String(64), index=True)  # git, gps, calendar, ...
    title: Mapped[str] = mapped_column(String(512))
    content: Mapped[str] = mapped_column(Text, default="")

    # PCME memory type: episodic | knowledge | social | goal
    memory_type: Mapped[str] = mapped_column(String(16), default="episodic", index=True)

    location: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    emotion: Mapped[str | None] = mapped_column(String(32), nullable=True)
    importance: Mapped[float] = mapped_column(Float, default=0.5)

    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    links: Mapped[list[MemoryEntity]] = relationship(
        back_populates="memory", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_memories_source_ts", "source", "ts"),
    )


class Entity(Base):
    """A node in the Life Graph: a person, project, goal, skill, or place."""

    __tablename__ = "entities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    type: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(256), index=True)
    # Running tally that drives region intensity / Knowledge Galaxy brightness.
    weight: Mapped[float] = mapped_column(Float, default=0.0)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    links: Mapped[list[MemoryEntity]] = relationship(
        back_populates="entity", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("type", "name", name="uq_entity_type_name"),)


class MemoryEntity(Base):
    """Edge between a memory and an entity (who/what/where it involved)."""

    __tablename__ = "memory_entities"

    memory_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("memories.id", ondelete="CASCADE"), primary_key=True
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(32), default="mentions")

    memory: Mapped[Memory] = relationship(back_populates="links")
    entity: Mapped[Entity] = relationship(back_populates="links")
