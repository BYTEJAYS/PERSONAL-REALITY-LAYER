<div align="center">

# 🧠 PRL — Personal Reality Layer

### A continuously evolving digital representation of a human life.

*Not a chatbot. Not a notes app. A second brain that collects, understands, and reconstructs your reality — and renders its own mind as a living particle brain.*

<br/>

![Next.js](https://img.shields.io/badge/Next.js-000000?style=for-the-badge&logo=nextdotjs&logoColor=white)
![React Three Fiber](https://img.shields.io/badge/React_Three_Fiber-000000?style=for-the-badge&logo=three.js&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Postgres](https://img.shields.io/badge/Postgres_+_pgvector-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![Neo4j](https://img.shields.io/badge/Neo4j-018BFF?style=for-the-badge&logo=neo4j&logoColor=white)
![Ollama](https://img.shields.io/badge/Local_LLM-000000?style=for-the-badge&logo=ollama&logoColor=white)

</div>

---

## ✨ What it does

PRL ingests the signals of a life — commits, locations, calendar, documents, conversations — and turns each into a **connected memory**. It builds a **Life Graph** of the people, projects, goals, and skills that recur, then lets you *ask your own history*:

> *"Where was I yesterday?"* · *"What project consumed most of my time last month?"*
> *"When did I first get into machine learning?"* · *"What am I neglecting?"*

…and answers instantly, from real data, with citations. Meanwhile the **Cognitive Core** visualises the AI's own mind as a particle brain that grows as your reality does.

---

## 🌟 Highlights

| | |
|---|---|
| 🧩 **Memory Engine** | One write-path for all of reality → Postgres (canonical + `pgvector` embeddings) + Neo4j (Life Graph). |
| 💬 **AI Chat** | Natural-language questions answered from your memories — intent detection → retrieval → grounded answers **with citations**. Local-LLM-first (Ollama), never hallucinates memories. |
| 🔭 **Insight Engine** | Evidence-backed observations — peak hours, primary focus, neglected projects, collaboration payoff, momentum. *No data → no claim.* |
| 🕰️ **Reality Reconstruction** | Rebuild any single day into a narrative from the memories that fall in it. |
| 🧠 **Cognitive Core** | A particle brain sampled from a **real anatomical brain mesh**, R3F + custom GLSL — the visible representation of the evolving mind. |
| 🔌 **Zero-key ingestion** | Seeds straight from your local `git log` — real commits become real memories, no API keys. |

---

## 🏗️ Architecture

```mermaid
flowchart LR
    subgraph S[" Reality Signals "]
        direction TB
        G([Git history])
        C([Calendar · soon])
        D([Documents · soon])
    end

    S --> ME{{Memory Engine}}

    ME --> PG[(Postgres<br/>+ pgvector)]
    ME --> NEO[(Neo4j<br/>Life Graph)]

    PG --> API[[FastAPI]]
    NEO --> API

    API --> CHAT[💬 AI Chat<br/>grounded + cited]
    API --> INS[🔭 Insight Engine]
    API --> REC[🕰️ Reconstruction]
    API --> BRAIN[🧠 Brain State]

    CHAT -.-> LLM([Local LLM · Ollama])
    BRAIN --> FE[["🧠 Cognitive Core<br/>Particle Brain"]]

    classDef store fill:#0d1117,stroke:#4169E1,color:#fff;
    classDef api fill:#0d1117,stroke:#009688,color:#fff;
    classDef fe fill:#0d1117,stroke:#a855f7,color:#fff;
    class PG,NEO store;
    class API api;
    class FE fe;
```

---

## 📂 Monorepo

```
personal-reality-layer/
├── backend/                 # FastAPI · the brain behind the brain
│   ├── app/
│   │   ├── memory_engine.py   # single write-path for all reality
│   │   ├── models.py          # Memory · Entity · MemoryEntity (+ pgvector)
│   │   ├── graph.py           # Neo4j Life Graph projection
│   │   ├── brain.py           # cognitive-region aggregation
│   │   ├── query_engine.py    # AI Chat — intent → retrieval → grounded answer
│   │   ├── insight_engine.py  # evidence-backed observations
│   │   ├── llm.py             # Ollama-first, Anthropic fallback
│   │   ├── ingestion/         # git connector + entity extraction
│   │   └── routers/           # /chat /insights /brain /memories /reconstruct /ingest
│   └── scripts/seed_from_repos.py
│
├── frontend/                # Next.js · the Cognitive Core
│   ├── components/
│   │   ├── ParticleBrain.tsx  # samples public/brain.obj → 200k+ particles
│   │   ├── BrainCanvas.tsx    # R3F canvas · orbit · auto-rotate
│   │   └── HUD.tsx            # glass overlay · live/mock · ask bar
│   └── public/brain.obj
│
└── docker-compose.yml       # Postgres+pgvector · Neo4j · Redis · API
```

---

## 🚀 Quickstart

### Backend — the full stack

> Requires **Docker Desktop**.

```bash
cp .env.example .env
docker compose up --build
```

| Service | URL |
|---|---|
| **API docs** | http://localhost:8000/docs |
| Neo4j Browser | http://localhost:7474 |
| Postgres | `localhost:5433` |
| Redis | `localhost:6380` |

### Frontend — the Cognitive Core

```bash
cd frontend
npm install
npm run dev          # → http://localhost:3001
```

Runs on mock data immediately; flips to **live** the moment the backend answers `/brain/state`.

---

## 🌱 Seed your real life

No API key — your local commits become memories:

```bash
cd backend
pip install -r requirements.txt
DATABASE_URL=postgresql+psycopg://prl:prl@localhost:5433/prl \
python -m scripts.seed_from_repos ~/your-repo-a ~/your-repo-b
```

Then ask your history:

```bash
curl -s localhost:8000/chat -X POST -H 'content-type: application/json' \
  -d '{"message":"What project am I neglecting?"}' | jq
curl -s localhost:8000/insights | jq
curl -s "localhost:8000/reconstruct/2026-05-29" | jq
```

---

## 🛰️ API surface

| Endpoint | Purpose |
|---|---|
| `POST /chat` | Ask your second brain — grounded answers with citations |
| `GET  /insights` | Evidence-backed observations about your life |
| `GET  /cognitive/model` | The digital twin — traits, knowledge distribution, evidence |
| `GET  /cognitive/predictions` | Probabilistic forecasts (burnout, completion, decay) |
| `GET  /cognitive/trends` | How interests/skills are rising, fading, emerging |
| `GET  /cognitive/patterns` | Discovered correlations — contemporaneous + time-lagged |
| `GET  /reconstruct/{day}` | Narrative reconstruction of a single day |
| `POST /memories` · `GET /memories` | Ingest / list & filter memories |
| `GET  /memories/search?q=` | Semantic (vector) search |
| `POST /ingest/git` | Ingest a local repo's history |
| `GET  /brain/state` | Live cognitive-region intensities (drives the particles) |
| `GET  /brain/focus?name=` | An entity's graph neighbourhood (the fly-through) |

Full interactive reference at **`/docs`** (OpenAPI / Swagger).

---

## 🗺️ Roadmap

- [x] Memory Engine · Brain API · git ingestion
- [x] Memory typing — episodic · knowledge · social · goal
- [x] AI Chat query engine (local-LLM-first, cited)
- [x] Insight Engine (evidence-grounded)
- [x] **Cognitive Model (L5)** — digital-twin traits with evidence
- [x] **Prediction Engine** — burnout · completion · habit stability · knowledge decay
- [x] **Trend Engine** — rising / fading / emerging / dormant interests
- [x] **Pattern Discovery (L4)** — contemporaneous + time-lagged correlations
- [x] Cognitive Core — particle brain from a real mesh
- [ ] More connectors — calendar · browser · documents · photos · GPS
- [ ] Reality Interface (Frontend 1) — Home · Timeline · Life Graph · Knowledge Galaxy
- [ ] Wire the particle brain to live `/brain/state`

---

<div align="center">

**The particle brain is not decoration — it is the visible representation of an evolving mind.**

*Every memory changes it. Every goal reshapes it. No two brains ever look the same.*

</div>
