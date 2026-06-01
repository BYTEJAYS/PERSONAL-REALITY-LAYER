"""PRL backend — Personal Reality Layer.

The Memory Engine spine: every input becomes a Memory stored canonically in
Postgres (with a pgvector embedding) and projected into the Neo4j Life Graph.
The Brain API aggregates that state into cognitive regions for the Cortex
particle-brain frontend.
"""

__version__ = "0.1.0"
