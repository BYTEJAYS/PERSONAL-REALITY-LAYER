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

### 4. Ollama  (root directory: `ollama/`) — the LLM voice

Optional but it's what turns Jerry's deterministic, template-y replies into a
real narrated voice. Runs as a **private** service (no public domain) that the
API reaches over Railway's IPv6 private network. See `ollama/Dockerfile` +
`ollama/entrypoint.sh` (model is pulled on first boot into a volume, not baked).

> ⚠️ **Cost & speed.** This service is always-on with a few GB of RAM, so it
> burns Railway credits continuously (~$5–15+/mo, more than the API). CPU
> inference is slow — expect ~15–40s/reply for `llama3.2:3b`. The frontend
> already allows a 90s companion timeout for this.

**Dashboard steps (do these in order):**

1. **New → GitHub Repo → `BYTEJAYS/PERSONAL-REALITY-LAYER`** (same project as the
   API). After it's added, open the service → **Settings → Build**:
   - **Root Directory**: `ollama`
   - Builder auto-detects `ollama/railway.json` (Dockerfile). Rename the service
     to `ollama` (Settings → name) — the API will reference it by this name.
2. **Settings → Networking**: do **NOT** generate a public domain. Leave it
   private (Railway gives it `ollama.railway.internal` automatically).
3. **Variables** (Raw Editor):
   ```
   OLLAMA_HOST=[::]:11434
   OLLAMA_MODEL=llama3.2:3b
   ```
   (The Dockerfile already sets these defaults; setting them here lets you swap
   the model later without a code change.)
4. **Settings → Volumes → Add Volume**, mount path **`/root/.ollama`**. This
   persists the downloaded model across restarts/redeploys (~2GB). Without it,
   every deploy re-downloads the model on boot.
5. **Deploy.** First boot downloads the model — watch the logs for
   `[entrypoint] ready — serving 'llama3.2:3b'` (a few minutes). The server
   answers `/` ("Ollama is running") almost immediately; the pull runs after.

**Then flip the API service to use it** (API service → Variables, change just
these — Raw Editor replaces ALL vars, so keep the rest):

| var | value |
|-----|-------|
| `LLM_PROVIDER` | `ollama` |
| `OLLAMA_URL` | `http://ollama.railway.internal:11434` |
| `LLM_MODEL` | `llama3.2:3b` |

Redeploy the API. Verify: `POST /companion/ask` (friend token) now returns
`"generated_by": "llm"` instead of `"deterministic"`. If Ollama is ever
unreachable the API silently falls back to deterministic answers (by design), so
this can't take Jerry down.

> **Gotcha — private networking is IPv6-only.** Ollama must bind `[::]` (done in
> the Dockerfile via `OLLAMA_HOST`). Binding `0.0.0.0` would be IPv4-only and the
> API's calls to `ollama.railway.internal` (an IPv6 address) would hang/refuse.

## Seeding the cloud DB — SYNTHETIC data only

> ⚠️ **A public demo must never hold real personal memories.** Do NOT restore
> `backups/prl_db_*.sql` and do NOT run `seed_from_repos` (your real repos) on a
> public deployment. Use the fictional demo persona, which lights up every cortex
> with zero real data.

Validate the dataset offline first (no DB needed):
```
cd backend && python scripts/seed_demo.py --check
```
Then seed the cloud Postgres (via its **public** TCP proxy host/port from Railway):
```
DATABASE_URL="postgresql+psycopg://<user>:<pass>@<railway-public-host>:<port>/<db>" \
  NEO4J_ENABLED=false python -m scripts.seed_demo
```
This ingests ~113 synthetic memories for "Alex Kumar" spanning 2019–2026:
milestones, recurring finances + an anomaly, health tests/meds, family
relations/recipe, an emotional arc (recent stress), a night-owl behaviour
pattern, and goals.

After seeding, every endpoint computes live from the cloud DB:
`/cognitive/*`, all `/cortex/*` (incl. emotional/social/behaviour), `/memory/*`
(events, aging, timemachine, compress, reconstruct), and `/reality/*` (world,
agents, simulate, evolution, …). The LLM steps stay deterministic unless you set
`LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY` (fine here — the data is fake).

---

# Friends Companion deployment (REAL data, friends-only)

> This is the "a version of me my friends can talk to" build. It uses your REAL
> data, but exposes only the discreet `/companion` voice to friends. Treat it as
> a privacy-critical deployment.

**How safety is enforced (already in the code):**
- `OWNER_TOKEN` set ⇒ a middleware locks every raw endpoint (exact finances,
  health, memories, provenance) to the owner. Friends physically cannot reach
  them — only `/companion/*`.
- `/companion` reasons from everything but **redacts before answering**: money &
  medical numbers are masked, private journal/self-analysis is never quoted,
  family/friends are kept vague (`companion.py`).
- Each friend gets their own token, so you can revoke one without affecting others.

**Env (API service):**

| var | value |
|-----|-------|
| `OWNER_TOKEN` | a long random secret (you) |
| `FRIEND_TOKENS` | `alice-xxxx,bob-yyyy,…` (one per friend) |
| `LLM_PROVIDER` | `ollama` (no API key — see Voice below) |
| `OLLAMA_URL` | `http://ollama:11434` (the cloud Ollama service) |
| `LLM_MODEL` | `llama3.2:3b` (realistic size for CPU inference) |
| `DATABASE_URL` | the demo/real Postgres (`+psycopg` driver) |
| `NEO4J_ENABLED` | `false` |

**Voice — cloud Ollama, NO API key.** Run the open model on your own box next to
the API. On a VPS:
```
LLM_MODEL=llama3.2:3b OLLAMA_URL=http://ollama:11434 \
  docker compose --profile voice up -d --build
```
That starts an `ollama` service, pulls the model once into a persistent volume,
and the API talks to it over the private network — zero keys, fully yours. (CPU
inference of a 3B model is a few seconds per reply for a handful of friends; bump
the box's RAM if it's tight. Railway can't run Ollama well — use a small VPS, e.g.
Hetzner/DO, for the voice box.) If Ollama is ever unreachable, the companion falls
back to grounded deterministic answers automatically.

**Frontend — the Vercel link your friends use.** Deploy `frontend/` to Vercel
with `NEXT_PUBLIC_API_URL=https://<api-domain>`. Share the **`/companion`** route:
`https://<your-vercel-app>/companion`. Friends enter their name + access code
(their `FRIEND_TOKENS` value), then chat. A "Correct / add info" toggle sends to
the quarantine queue for your review. (The brain visual stays at `/`; the
dashboard at `/dashboard` — those hit owner-gated endpoints, so keep them for you.)

**Seeding with your real data (private — do this yourself, not on a shared box):**
restore your dump or run `seed_from_repos`/`ingest/text` against the instance.
Because `OWNER_TOKEN` gates ingestion, only you can load or update it.

**Friends use it like:**
```
curl -X POST https://<api>/companion/ask \
  -H "x-access-token: alice-xxxx" -H "content-type: application/json" \
  -d '{"question":"how would Jay react if his startup failed?"}'
```
A friend hitting `/cortex/finance` or `/memories` gets `403 Owner access only`.

**Friends help it learn (without being able to rewrite you):**
- `POST /companion/contribute` `{ "text": "...", "submitter": "Sam" }` — a friend
  shares something about you. Facts/corrections land in **quarantine** (stored
  inert: no embedding, no links, never used in answers); questions are just logged.
- `GET /companion/pending` (owner) — your review queue.
- `POST /companion/review` (owner) `{ "memory_id": "...", "approve": true }` —
  approve → it becomes a real memory, credited to the friend and marked verified;
  reject → discarded. Nothing a friend says is treated as true about you until you
  confirm it.
- `GET /companion/questions` (owner) — what friends keep asking (signal for what
  to fill in).

**Still on you (not technical):** the people in your data (family, friends,
doctor) didn't consent to being queried. The redaction softens their details, but
consider telling the friends you invite what this is — and only invite people you
trust with the real, unfiltered *you*.
