from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from .. import ingest_service
from ..db import get_db
from ..ingestion.git_ingest import ingest_repo
from ..ingestion.text_ingest import ingest_text
from ..schemas import ConnectorRunIn, GitIngestIn, TextIngestIn

router = APIRouter(prefix="/ingest", tags=["ingest"])


class ResetIn(BaseModel):
    confirm: str  # must equal "WIPE" — guards against accidental fire


@router.post("/reset")
def reset_all(body: ResetIn, db: Session = Depends(get_db)):
    """Owner-only: wipe ALL memory data for a clean re-ingest. Irreversible.

    Truncates memories, entities and their links. Owner-gated by the global
    owner_guard middleware; the {"confirm":"WIPE"} body is a second safety.
    """
    if body.confirm != "WIPE":
        raise HTTPException(status_code=400, detail='Send {"confirm": "WIPE"} to proceed.')
    before = db.execute(text("SELECT count(*) FROM memories")).scalar() or 0
    db.execute(text("TRUNCATE memories, entities, memory_entities RESTART IDENTITY CASCADE"))
    db.commit()
    return {"wiped": True, "memories_deleted": int(before)}


@router.get("/connectors")
def list_connectors():
    """All Layer-1 connectors and whether each can read on this machine."""
    return ingest_service.list_connectors()


@router.post("/run")
def run_connector(payload: ConnectorRunIn, db: Session = Depends(get_db)):
    """Run a connector (git/browser/files/shell) into the Memory Engine."""
    try:
        return ingest_service.run_connector(db, payload.connector, **payload.options)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"ingest failed: {exc}")


@router.post("/git")
def ingest_git(payload: GitIngestIn, db: Session = Depends(get_db)):
    """Ingest a local git repository's history into the Memory Engine.

    NOTE: `path` is resolved on the *API process's* filesystem. When the API
    runs in Docker, mount the repo into the container or run the seed script
    on the host instead.
    """
    try:
        return ingest_repo(
            db, payload.path, project=payload.project,
            limit=payload.limit, author_filter=payload.author_filter,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # surface git errors cleanly
        raise HTTPException(status_code=500, detail=f"git ingest failed: {exc}")


@router.post("/text")
def ingest_free_text(payload: TextIngestIn, db: Session = Depends(get_db)):
    """Ingest free-text (a journal entry, brain-dump, reflection) as a memory.

    Mines the text for goals (populating the goal region) and links any skills
    or existing projects it mentions. This is the path for the self-reflective
    'why' the you-model learns most from.
    """
    return ingest_text(
        db, payload.text, source=payload.source,
        title=payload.title, importance=payload.importance, emotion=payload.emotion,
    )
