"""Connector framework — Layer 1 multimodal ingestion.

Each connector reads one source (git, browser, files, …) and yields normalized
`RawMemory` records. Connectors are deliberately dependency-free (stdlib only),
so the same code path feeds both the live API (→ Memory Engine → Postgres) and
the offline trainer (no infrastructure). Privacy: every connector reads only
local data and nothing is ever sent anywhere.
"""
