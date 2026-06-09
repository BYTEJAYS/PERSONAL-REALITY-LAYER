#!/usr/bin/env bash
# start-prl-local.sh — run the FULL PRL backend locally with NO Docker.
#
# Uses a conda env (Postgres 16 + pgvector + Python deps) created once at
# ~/miniforge3/envs/prl, and a local Postgres data dir at ~/.prl-local-pg.
# Embeddings use the offline hashing provider (no torch needed); Neo4j + LLM off.
# This is the path that lets ASCENSION's bridge actually round-trip locally.
#
# Shut it down with ./stop-prl-local.sh
set -euo pipefail

ENV_DIR="$HOME/miniforge3/envs/prl"
PGBIN="$ENV_DIR/bin"
PGDATA="$HOME/.prl-local-pg"
PGPORT=5433
DBNAME=prl
DBUSER="$(whoami)"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$HOME/.prl-local"
mkdir -p "$LOG_DIR"

if [ ! -x "$PGBIN/postgres" ]; then
  echo "✗ conda env not found at $ENV_DIR"
  echo "  create it once:  ~/miniforge3/bin/conda create -y -n prl -c conda-forge python=3.12 postgresql=16 pgvector"
  echo "  then:            $ENV_DIR/bin/pip install fastapi 'uvicorn[standard]' pydantic pydantic-settings SQLAlchemy 'psycopg[binary]' pgvector neo4j redis python-dateutil httpx"
  exit 1
fi

# 1) Postgres ----------------------------------------------------------------
if "$PGBIN/pg_isready" -p "$PGPORT" -q 2>/dev/null; then
  echo "✓ Postgres already running (:$PGPORT)"
else
  if [ ! -d "$PGDATA" ]; then
    echo "▸ first run — initialising Postgres data dir..."
    "$PGBIN/initdb" -D "$PGDATA" -U "$DBUSER" --auth-local=trust --auth-host=trust >"$LOG_DIR/initdb.log" 2>&1
  fi
  echo "▸ starting Postgres..."
  "$PGBIN/pg_ctl" -D "$PGDATA" -o "-p $PGPORT" -l "$PGDATA/server.log" start
  for _ in $(seq 1 20); do "$PGBIN/pg_isready" -p "$PGPORT" -q 2>/dev/null && break; sleep 0.5; done
fi

# db + pgvector extension (idempotent)
if ! "$PGBIN/psql" -p "$PGPORT" -U "$DBUSER" -lqt 2>/dev/null | cut -d'|' -f1 | grep -qw "$DBNAME"; then
  echo "▸ creating database '$DBNAME'..."
  "$PGBIN/createdb" -p "$PGPORT" -U "$DBUSER" "$DBNAME"
fi
"$PGBIN/psql" -p "$PGPORT" -U "$DBUSER" -d "$DBNAME" -qc "CREATE EXTENSION IF NOT EXISTS vector;" >/dev/null
echo "✓ Postgres ready (db '$DBNAME', pgvector on :$PGPORT)"

# 2) PRL backend -------------------------------------------------------------
if curl -s http://localhost:8000/health -m 2 >/dev/null 2>&1; then
  echo "✓ PRL API already running (:8000)"
else
  echo "▸ starting PRL API..."
  ( cd "$ROOT/backend" && \
    DATABASE_URL="postgresql+psycopg://$DBUSER@localhost:$PGPORT/$DBNAME" \
    EMBEDDING_PROVIDER=local EMBEDDING_DIM=384 \
    NEO4J_ENABLED=false LLM_PROVIDER=none \
    nohup "$PGBIN/uvicorn" app.main:app --host 0.0.0.0 --port 8000 \
      >"$LOG_DIR/prl.log" 2>&1 & )
  for _ in $(seq 1 30); do curl -s http://localhost:8000/health -m 2 >/dev/null 2>&1 && break; sleep 1; done
  if curl -s http://localhost:8000/health -m 3 >/dev/null 2>&1; then
    echo "✓ PRL API up (:8000)"
  else
    echo "✗ PRL API didn't come up. Last log lines:"
    tail -n 15 "$LOG_DIR/prl.log" 2>/dev/null | sed 's/^/    /'
    exit 1
  fi
fi

cat <<EOF

════════════════════════════════════════════════════════════════
  PRL is running LOCALLY (no Docker).

  ▸ API:      http://localhost:8000/health
  ▸ Postgres: localhost:$PGPORT  (db '$DBNAME', data in $PGDATA)
  ▸ Voice:    deterministic (LLM off); embeddings = hashing (offline)

  ASCENSION's bridge points here by default — open the game and use the
  PRL Bridge card (Character page) to feed it your habits/journal/quests.

  • Stop it all:   ./stop-prl-local.sh
════════════════════════════════════════════════════════════════
EOF
