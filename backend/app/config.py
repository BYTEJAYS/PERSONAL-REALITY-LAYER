from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Postgres — canonical memories + pgvector. Default targets the compose
    # service; override with DATABASE_URL for a host-side run against port 5433.
    database_url: str = "postgresql+psycopg://prl:prl@localhost:5433/prl"

    @field_validator("database_url", mode="before")
    @classmethod
    def _force_psycopg3(cls, v: str) -> str:
        # Railway (and most managed Postgres) inject a stock "postgresql://..."
        # URL, which SQLAlchemy maps to the legacy psycopg2 dialect — but only
        # psycopg v3 is installed. Pin the driver so we never import psycopg2.
        if isinstance(v, str):
            if v.startswith("postgres://"):
                v = "postgresql://" + v[len("postgres://"):]
            if v.startswith("postgresql://"):
                v = "postgresql+psycopg://" + v[len("postgresql://"):]
        return v

    # Neo4j — the Life Graph.
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "prlpassword"
    # When false (e.g. Neo4j not up yet), graph writes are skipped, not fatal.
    neo4j_enabled: bool = True

    redis_url: str = "redis://localhost:6380/0"

    # Semantic memory index. "sentence_transformers" = real local encoder
    # (meaning-aware recall); "local" = hashing fallback (token-overlap only);
    # "openai" = hosted, opt-in.
    embedding_provider: str = "sentence_transformers"
    embedding_dim: int = 384
    st_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    openai_api_key: str | None = None

    # AI Chat layer. Local-first: talk to Ollama if it's running, otherwise the
    # query engine falls back to deterministic, evidence-grounded answers.
    llm_provider: str = "ollama"  # "ollama" | "anthropic" | "none"
    ollama_url: str = "http://localhost:11434"
    llm_model: str = "llama3.1"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-haiku-4-5-20251001"

    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:3001"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
