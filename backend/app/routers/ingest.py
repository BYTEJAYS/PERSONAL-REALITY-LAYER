from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import ingest_service
from ..db import get_db
from ..ingestion.git_ingest import ingest_repo
from ..schemas import ConnectorRunIn, GitIngestIn

router = APIRouter(prefix="/ingest", tags=["ingest"])


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
