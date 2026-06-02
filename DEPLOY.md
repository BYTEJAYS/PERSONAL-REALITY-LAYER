# Deploying PRL to Railway

Lean cloud v1: **Postgres (pgvector) + API + brain frontend**. Neo4j and Redis
are off for now (`graph.py` is non-fatal when `NEO4J_ENABLED=false`); add them
later as separate services.

## One-time, must be done by you (browser/credentials)

1. Create a Railway account: https://railway.app (sign in with GitHub — same
   account that owns `BYTEJAYS/PERSONAL-REALITY-LAYER`).
2. Log the CLI in (opens a browser):
   ```
   railway login
   ```
That's the only manual part. Everything below can be driven from the terminal.

## Services

### 1. Postgres with pgvector
The app runs `CREATE EXTENSION vector`, so the DB **must** ship pgvector. Use the
Railway **pgvector** template (Dashboard → New → Database → "pgvector"), or deploy
the `pgvector/pgvector:pg16` image as a service. Plain Railway Postgres may not
have the extension.

### 2. API  (root directory: `backend/`)
Builder: Dockerfile (see `backend/railway.json`). Env vars:

| var | value |
|-----|-------|
| `DATABASE_URL` | `postgresql+psycopg://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@${{Postgres.RAILWAY_PRIVATE_DOMAIN}}:5432/${{Postgres.PGDATABASE}}` |
| `NEO4J_ENABLED` | `false` |
| `EMBEDDING_PROVIDER` | `local` |
| `EMBEDDING_DIM` | `384` |
| `LLM_PROVIDER` | `none` (deterministic chat; no Ollama in cloud) |
| `CORS_ORIGINS` | `["https://<frontend-domain>"]` (set after frontend deploy) |

Note the `+psycopg` driver — Railway's stock `DATABASE_URL` uses plain
`postgresql://` which SQLAlchemy won't load with psycopg3. Override it as above.

Healthcheck: `/health`. Generate a public domain for this service and copy it.

### 3. Frontend  (root directory: `frontend/`)
Builder: Nixpacks (`npm ci → build → start`, port honored via `$PORT`). Env var,
**set before the build** (Next bakes `NEXT_PUBLIC_*` at build time):

| var | value |
|-----|-------|
| `NEXT_PUBLIC_API_URL` | `https://<api-public-domain>` |

Then redeploy so the build picks it up. Pages: `/` (Spline brain) and `/dashboard`.

## Seeding the cloud DB (no host Python needed)
Run the in-container seeder against the cloud Postgres public URL:
```
docker compose exec api env \
  DATABASE_URL="postgresql+psycopg://<user>:<pass>@<railway-public-host>:<port>/<db>" \
  NEO4J_ENABLED=false \
  python -m scripts.seed_from_repos /host/transaction-graph-intelligence \
    /host/synthetic-genesis /host/echo-interrogation /host/party-racer \
    /host/bling-blue-team /host/github-profile /host/prl
```
(Use the Postgres service's **public** TCP proxy host/port from Railway, not the
private domain, since this runs from your laptop.)

After seeding, every `/cognitive/*` endpoint computes live from the cloud DB.
