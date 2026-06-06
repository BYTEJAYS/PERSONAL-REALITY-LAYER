from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class EntityRefIn(BaseModel):
    type: str = Field(pattern="^(person|project|goal|skill|place)$")
    name: str
    role: str = "mentions"


class MemoryIn(BaseModel):
    ts: datetime
    source: str = "manual"
    title: str
    content: str = ""
    location: dict | None = None
    emotion: str | None = None
    importance: float = 0.5
    entities: list[EntityRefIn] = []
    meta: dict = {}
    dedupe_key: str | None = None


class EntityOut(BaseModel):
    type: str
    name: str
    role: str


class MemoryOut(BaseModel):
    id: uuid.UUID
    ts: datetime
    source: str
    title: str
    content: str
    memory_type: str
    location: dict | None
    emotion: str | None
    importance: float
    entities: list[EntityOut]

    @classmethod
    def from_model(cls, m) -> "MemoryOut":
        return cls(
            id=m.id, ts=m.ts, source=m.source, title=m.title, content=m.content,
            memory_type=m.memory_type,
            location=m.location, emotion=m.emotion, importance=m.importance,
            entities=[
                EntityOut(type=l.entity.type, name=l.entity.name, role=l.role)
                for l in m.links
            ],
        )


class RegionState(BaseModel):
    region: str
    count: int
    weight: float
    intensity: float


class BrainState(BaseModel):
    total_memories: int
    total_entities: int
    regions: list[RegionState]
    neo4j: bool


class ChatTurn(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatIn(BaseModel):
    message: str
    # Optional prior turns so the brain holds a conversation (most recent last).
    history: list[ChatTurn] = []


class ChatOut(BaseModel):
    answer: str
    intent: str
    llm_used: bool
    citations: list[dict]
    data: dict


class DecideOption(BaseModel):
    name: str
    # Feature values in [0,1] on the You-Model axes (novelty, continuation,
    # alignment, solo, depth, momentum, goal_fit). Omit any you don't know.
    features: dict[str, float] = {}


class DecideIn(BaseModel):
    options: list[DecideOption]


class CouncilIn(BaseModel):
    question: str


class ConnectorRunIn(BaseModel):
    connector: str
    options: dict = {}


class GitIngestIn(BaseModel):
    path: str
    project: str | None = None  # defaults to repo dir name
    limit: int = 500
    author_filter: str | None = None  # only commits whose author contains this


class TextIngestIn(BaseModel):
    text: str
    source: str = "note"
    title: str | None = None       # defaults to the first line
    importance: float = 0.6
    emotion: str | None = None


class JournalIn(BaseModel):
    text: str
    ts: datetime | None = None     # when it happened; defaults to now (UTC)
    title: str | None = None       # defaults to "Journal · <date> — <first line>"
    importance: float = 0.6
    emotion: str | None = None     # override the auto-detected dominant emotion
    location: dict | None = None
