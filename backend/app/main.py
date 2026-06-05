from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import graph
from .config import get_settings
from .db import init_db
from .routers import (
    brain, chat, cognitive, cortex, ingest, insights, memories, memory, reality,
    reconstruct,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("prl")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    graph.ensure_constraints()
    log.info("PRL backend ready (neo4j=%s)", graph.ping())
    yield


app = FastAPI(title="PRL — Personal Reality Layer", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(memories.router)
app.include_router(brain.router)
app.include_router(reconstruct.router)
app.include_router(ingest.router)
app.include_router(chat.router)
app.include_router(insights.router)
app.include_router(cognitive.router)
app.include_router(cortex.router)
app.include_router(memory.router)
app.include_router(reality.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "version": app.version, "neo4j": graph.ping()}


@app.get("/", tags=["meta"])
def root():
    return {
        "name": "Personal Reality Layer",
        "docs": "/docs",
        "endpoints": ["/health", "/chat", "/insights", "/cognitive/model",
                      "/cognitive/predictions", "/cognitive/trends",
                      "/cognitive/simulate", "/cognitive/chapters", "/cognitive/identity",
                      "/cognitive/habits", "/cognitive/decisions", "/cognitive/blind-spots",
                      "/cognitive/os", "/cognitive/knowledge-graph", "/cognitive/learning",
                      "/cortex/finance", "/cortex/health", "/cortex/family",
                      "/cortex/emotional", "/cortex/social", "/cortex/behaviour",
                      "/memory/events", "/memory/aging", "/memory/duplicates",
                      "/memory/patterns", "/memory/fractal", "/memory/compress",
                      "/memory/reconstruct", "/memory/timemachine",
                      "/reality/importance", "/reality/confidence", "/reality/economy",
                      "/reality/versioning", "/reality/curiosity", "/reality/compile",
                      "/brain/state", "/memories", "/reconstruct/{day}", "/ingest/git"],
    }
