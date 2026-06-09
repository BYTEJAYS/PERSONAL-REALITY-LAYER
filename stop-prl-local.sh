#!/usr/bin/env bash
# stop-prl-local.sh — stop the local (no-Docker) PRL stack: API + Postgres.
# Data persists in ~/.prl-local-pg; restart anytime with ./start-prl-local.sh
PGBIN="$HOME/miniforge3/envs/prl/bin"
PGDATA="$HOME/.prl-local-pg"

echo "Stopping local PRL…"

# PRL API (uvicorn for this app)
if pgrep -f "uvicorn app.main:app --host 0.0.0.0 --port 8000" >/dev/null 2>&1; then
  pkill -f "uvicorn app.main:app --host 0.0.0.0 --port 8000" 2>/dev/null || true
  sleep 1
  echo "✓ PRL API stopped"
else
  echo "· PRL API wasn't running"
fi

# Postgres
if [ -x "$PGBIN/pg_ctl" ] && "$PGBIN/pg_isready" -p 5433 -q 2>/dev/null; then
  "$PGBIN/pg_ctl" -D "$PGDATA" stop -m fast >/dev/null 2>&1 && echo "✓ Postgres stopped" || echo "✗ couldn't stop Postgres (try: $PGBIN/pg_ctl -D $PGDATA stop)"
else
  echo "· Postgres wasn't running"
fi

echo "Done. Data preserved in $PGDATA."
