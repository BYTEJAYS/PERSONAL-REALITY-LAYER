from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import graph
from .config import get_settings
from .db import init_db
from .routers import (
    brain, chat, cognitive, companion, cortex, ingest, insights, memories, memory,
    reality, reconstruct,
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

# Friends-deployment guard: when OWNER_TOKEN is set, only the owner may reach the
# raw endpoints. Friends (friend tokens) are limited to the discreet /companion
# voice, which applies record redaction. With no OWNER_TOKEN, the gate is open
# (local/dev). This is what makes "friends can talk to me" safe to host with real
# data — they never reach exact finances/health/memories.
_OWNER_OPEN_PATHS = ("/health", "/", "/docs", "/openapi.json", "/redoc")


@app.middleware("http")
async def owner_guard(request, call_next):
    import os
    from fastapi.responses import JSONResponse

    owner = os.getenv("OWNER_TOKEN")
    path = request.url.path
    if (owner and request.method != "OPTIONS"
            and not path.startswith("/companion")
            and path not in _OWNER_OPEN_PATHS):
        if request.headers.get("x-access-token") != owner:
            return JSONResponse(status_code=403,
                                content={"detail": "Owner access only. Friends use /companion."})
    return await call_next(request)

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
app.include_router(companion.router)


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
                      "/reality/world", "/reality/agents", "/reality/ask",
                      "/reality/evolution", "/reality/provenance", "/reality/simulate",
                      "/reality/capture", "/companion/ask", "/companion/about",
                      "/companion/contribute", "/companion/pending", "/companion/review",
                      "/brain/state", "/memories", "/reconstruct/{day}", "/ingest/git"],
    }
