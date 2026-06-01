# PRL — Personal Reality Layer

A continuously evolving digital representation of a human life. This repo is the
**backend core**: the Memory Engine that turns every life signal into a
connected memory, and the Brain API that exposes the AI's live cognitive state
to the particle-brain frontend.

> Status: backend vertical slice. Frontends (Reality Interface + Cognitive
> Core) are not in this repo yet.

## Architecture

```
ingestion (git, …) ──▶ Memory Engine ──┬──▶ Postgres + pgvector   (canonical memories + embeddings)
                                        └──▶ Neo4j Life Graph      (entities + relationships)
                                              │
                                  Brain API ──┴──▶ cognitive regions / focus / reconstruction
```

- **Postgres + pgvector** — every `Memory` (id, ts, source, location, emotion,
  importance, embedding, entities) stored canonically; semantic search via
  cosine distance.
- **Neo4j** — the Life Graph. Entities (person/project/goal/skill/place) and
  their co-occurrence relationships, for "what's connected to TGIE?" traversal.
- **Brain API** — aggregates the store into the five cognitive regions
  (memory, knowledge, project, goal, social) with real, data-driven intensities.

## Run the stack

Requires **Docker Desktop** (not yet installed on this machine — install from
https://www.docker.com/products/docker-desktop/, then `open -a Docker`).

```bash
cd prl
cp .env.example .env
docker compose up --build
```

Services:

| Service  | URL                          |
|----------|------------------------------|
| API      | http://localhost:8000/docs   |
| Neo4j    | http://localhost:7474        |
| Postgres | localhost:5433               |
| Redis    | localhost:6380               |

## Seed real data from your git repos

No API key — reads local `git log` and turns commits into memories.

```bash
# With the stack up, from the host:
cd prl/backend
pip install -r requirements.txt   # for the host-side seeder
DATABASE_URL=postgresql+psycopg://prl:prl@localhost:5433/prl \
NEO4J_URI=bolt://localhost:7687 \
python -m scripts.seed_from_repos \
  ~/transaction-graph-intelligence ~/synthetic-genesis ~/echo-interrogation
```

Then watch the brain fill up:

```bash
curl localhost:8000/brain/state | jq
curl "localhost:8000/reconstruct/2026-05-29" | jq
curl "localhost:8000/memories/search?q=fraud%20detection" | jq
curl "localhost:8000/brain/focus?type=project&name=synthetic-genesis" | jq
```

## API surface

| Endpoint                       | Purpose                                        |
|--------------------------------|------------------------------------------------|
| `POST /memories`               | Ingest one memory (any source)                 |
| `GET  /memories`               | List / filter by source + date range           |
| `GET  /memories/search?q=`     | Semantic (vector) search                       |
| `POST /ingest/git`             | Ingest a local repo's history                  |
| `GET  /brain/state`            | Live region intensities (drives the particles) |
| `GET  /brain/entities`         | Brightest nodes (Knowledge Galaxy)             |
| `GET  /brain/focus?name=`      | Entity neighborhood (the fly-through)          |
| `GET  /reconstruct/{day}`      | Reality reconstruction + narrative for a day   |

## Next

- Frontend 2 (Cortex): R3F particle brain consuming `/brain/state`.
- More connectors: GPS, calendar, browser, documents, photos.
- Celery workers for scheduled ingestion; Insight + Prediction engines.
