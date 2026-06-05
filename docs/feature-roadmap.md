# PRL Feature Roadmap — Build Status

> Living status map of the 23-module PRL (Personal Reality Ledger) architecture.
> **BUILT** = implemented + unit-tested · **PARTIAL** = core exists, pieces missing · **GAP** = not started.
> Backend cores are pure/DB-free and unit-tested (70/70 on host stdlib); DB adapters need Postgres.

## Core Modules

| # | Module | Status | Implementation |
|---|--------|--------|----------------|
| 1 | Memory Capture Engine | 🟡 PARTIAL | `ingestion/git_ingest.py`, `ingestion/text_ingest.py`, `memory_engine.py`. **Missing:** media ingestion (photos/audio/PDF), OCR, speech-to-text, face/object detection |
| 2 | Event Engine | ✅ BUILT | `events.py` — detection, clustering, summarization, importance, timeline |
| 3 | Memory Graph | ✅ BUILT | `graph.py` (Neo4j), `embeddings.py` + `query_engine.py` semantic search |
| 4 | Family Cortex | ✅ BUILT | `family_cortex.py` — tree, stories, recipes, dates. *(voice preservation = GAP)* |
| 5 | Health Cortex | ✅ BUILT | `health_cortex.py` — meds, labs, visits, reminders, timelines |
| 6 | Finance Cortex | ✅ BUILT | `finance_cortex.py` — spend, recurring bills, anomalies, forecasts |
| 7 | Knowledge Cortex | ✅ BUILT | `knowledge_graph.py`, `learning_model.py` — skills, retention, evolution |
| 8 | Behaviour Cortex | ✅ BUILT | `behaviour_cortex.py` + `rhythm.py` — focus window, weekday profile, consistency |
| 9 | Reflection Cortex | ✅ BUILT | `insight_engine.py` — evidence-grounded reviews/insights |
| 10 | Prediction Cortex | ✅ BUILT | `prediction_engine.py` + finance recurring/upcoming bills |
| 11 | Search Across Life | 🟡 PARTIAL | `query_engine.py` (`/chat`) NL + semantic search. **Missing:** cross-modal retrieval (no media indexed yet) |
| 12 | Time Machine | ✅ BUILT | `time_machine.py` — day/month/year/decade navigation + zoom |
| 13 | Memory Aging System | ✅ BUILT | `memory_aging.py` + `compressor.py` — tiers, smart compression, raw expiry |
| 14 | Dream Cortex | 🟡 PARTIAL | goals via `text_ingest.detect_goals` + `identity.py`. **Missing:** dedicated bucket-list/goal-decomposition surface |
| 15 | Project Cortex | ✅ BUILT | git ingestion + `decision_genome.py` + project entities |
| 16 | Emotional Cortex | ✅ BUILT | `emotional_cortex.py` — mood, emotion mix, mood timeline, stress trend |
| 17 | Social Cortex | ✅ BUILT | `social_cortex.py` — interaction frequency, inner circle, drift |
| 18 | Digital Twin | ✅ BUILT | `you_model.py`, `cognitive_model.py`, `self_model.py` |
| 19 | Legacy Cortex | 🟡 PARTIAL | story/recipe preservation in `family_cortex.py`. **Missing:** voice cloning, advice archive |
| 20 | Cognitive Compression Engine | ✅ BUILT | `compressor.py` — raw → summary → Memory DNA |
| 21 | Memory DNA Engine | ✅ BUILT | `compressor.memory_dna` + `embeddings.py` latent vectors |
| 22 | Generative Reconstruction | ✅ BUILT | `reconstructor.py` — recreate a labelled recollection from DNA |
| 23 | Personal Life OS | ✅ BUILT | `personal_os.py` — current→desired→distance→obstacles→leverage |

**Score: 18 BUILT · 4 PARTIAL · 1 (Reality Engine, below) GAP.**

## Reality Engine (unified world model)
🟡 PARTIAL — `brain.py` aggregates the cognitive regions and `personal_os.py` unifies the cortexes into one navigation map, but there is no single queryable world-model object yet.

## Moonshot Features (all 🔴 GAP, longer horizon)
| Feature | Notes |
|---------|-------|
| Digital Immortality | Depends on Legacy Cortex (voice/advice) first |
| Personal World Model / AI Life Simulator | `life_sim.py` already projects trajectories + counterfactuals — the seed exists |
| Memory Marketplace | Needs sharing/permission layer; not started |
| Reality Replay | `reconstructor.py` + `time_machine.py` are the building blocks |
| Human Knowledge Preservation | Cross-user aggregation; not started |

## Known cross-cutting blockers
- **Media ingestion** unlocks modules 1 & 11 fully — needs heavy deps (OCR/STT/vision models).
- **Postgres** (Docker) required to run any DB adapter live — Docker currently uninstalled.
- **Ollama** required for the LLM steps (compression summaries, reconstruction narratives, voice); deterministic fallbacks run until then.
