"""Configuration + environment resolution for AI context integration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


def _as_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _as_int(value: object, *, default: int, minimum: int = 0) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= minimum else default


def _as_str(value: object, *, default: str) -> str:
    if isinstance(value, str):
        text = value.strip()
        if text:
            return text
    return default


@dataclass(frozen=True)
class AISettings:
    enabled: bool
    include_in_review: bool

    embedding_model: str
    embedding_dimensions: int | None
    retrieval_top_k: int
    rerank_top_n: int
    chunk_chars: int
    chunk_overlap_chars: int
    cohere_rerank_model: str

    openai_api_key: str | None
    cohere_api_key: str | None
    turbopuffer_api_key: str | None

    turbopuffer_namespace: str
    turbopuffer_region: str | None

    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str | None
    neo4j_database: str
    temporal_coupling_max_commits: int = 240

    @property
    def has_openai(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def has_cohere(self) -> bool:
        return bool(self.cohere_api_key)

    @property
    def has_turbopuffer(self) -> bool:
        return bool(self.turbopuffer_api_key)

    @property
    def has_neo4j(self) -> bool:
        return bool(self.neo4j_uri and self.neo4j_user and self.neo4j_password)


def resolve_ai_settings(config: dict[str, Any] | None) -> AISettings:
    """Resolve AI settings from config + environment variables."""
    cfg = config if isinstance(config, dict) else {}

    enabled = _as_bool(
        os.environ.get("STRUCTORIUM_AI_ENABLED", cfg.get("ai_enabled")),
        default=False,
    )
    include_in_review = _as_bool(
        os.environ.get(
            "STRUCTORIUM_AI_INCLUDE_IN_REVIEW",
            cfg.get("ai_include_in_review"),
        ),
        default=True,
    )

    embedding_model = _as_str(
        os.environ.get(
            "STRUCTORIUM_EMBEDDING_MODEL",
            os.environ.get("OPENAI_EMBED_MODEL", cfg.get("ai_embedding_model")),
        ),
        default="text-embedding-3-large",
    )
    embedding_dimensions_raw = _as_int(
        os.environ.get(
            "STRUCTORIUM_EMBEDDING_DIMENSIONS",
            os.environ.get(
                "OPENAI_EMBED_DIMENSIONS",
                cfg.get("ai_embedding_dimensions", 0),
            ),
        ),
        default=0,
        minimum=0,
    )
    embedding_dimensions = embedding_dimensions_raw or None
    cohere_rerank_model = _as_str(
        os.environ.get(
            "STRUCTORIUM_COHERE_RERANK_MODEL",
            os.environ.get("COHERE_RERANK_MODEL", cfg.get("ai_cohere_rerank_model")),
        ),
        default="rerank-v3.5",
    )

    retrieval_top_k = _as_int(
        os.environ.get("STRUCTORIUM_AI_RETRIEVAL_TOP_K", cfg.get("ai_retrieval_top_k")),
        default=24,
        minimum=1,
    )
    rerank_top_n = _as_int(
        os.environ.get("STRUCTORIUM_AI_RERANK_TOP_N", cfg.get("ai_rerank_top_n")),
        default=10,
        minimum=1,
    )

    chunk_chars = _as_int(
        os.environ.get("STRUCTORIUM_AI_CHUNK_CHARS", cfg.get("ai_chunk_chars")),
        default=1800,
        minimum=300,
    )
    chunk_overlap_chars = _as_int(
        os.environ.get(
            "STRUCTORIUM_AI_CHUNK_OVERLAP_CHARS",
            cfg.get("ai_chunk_overlap_chars"),
        ),
        default=240,
        minimum=0,
    )
    if chunk_overlap_chars >= chunk_chars:
        chunk_overlap_chars = max(0, chunk_chars // 4)

    temporal_coupling_max_commits = _as_int(
        os.environ.get(
            "STRUCTORIUM_AI_TEMPORAL_MAX_COMMITS",
            cfg.get("ai_temporal_max_commits"),
        ),
        default=240,
        minimum=20,
    )
    openai_api_key = _as_str(os.environ.get("OPENAI_API_KEY"), default="") or None
    cohere_api_key = _as_str(os.environ.get("COHERE_API_KEY"), default="") or None
    turbopuffer_api_key = (
        _as_str(os.environ.get("TURBOPUFFER_API_KEY"), default="") or None
    )

    namespace_raw = _as_str(
        os.environ.get(
            "TURBOPUFFER_NAMESPACE",
            os.environ.get(
                "STRUCTORIUM_TURBOPUFFER_NAMESPACE",
                cfg.get("ai_turbopuffer_namespace"),
            ),
        ),
        default="",
    )
    namespace_prefix = _as_str(
        os.environ.get(
            "TURBOPUFFER_NAMESPACE_PREFIX",
            os.environ.get("STRUCTORIUM_TURBOPUFFER_NAMESPACE_PREFIX"),
        ),
        default="",
    )
    if namespace_raw:
        turbopuffer_namespace = namespace_raw
    elif namespace_prefix:
        turbopuffer_namespace = f"{namespace_prefix}structorium-code"
    else:
        turbopuffer_namespace = "structorium-code"
    region_raw = _as_str(
        os.environ.get(
            "TURBOPUFFER_REGION",
            os.environ.get(
                "STRUCTORIUM_TURBOPUFFER_REGION",
                cfg.get("ai_turbopuffer_region"),
            ),
        ),
        default="",
    )
    turbopuffer_region = region_raw or None

    neo4j_uri = _as_str(
        os.environ.get("NEO4J_URI", cfg.get("ai_neo4j_uri")),
        default="bolt://localhost:7687",
    )
    neo4j_user = _as_str(
        os.environ.get("NEO4J_USERNAME", cfg.get("ai_neo4j_user")),
        default="neo4j",
    )
    neo4j_password = _as_str(
        os.environ.get("NEO4J_PASSWORD", os.environ.get("NEO4J_PASS")),
        default="",
    ) or None
    neo4j_database = _as_str(
        os.environ.get("NEO4J_DATABASE", cfg.get("ai_neo4j_database")),
        default="neo4j",
    )

    return AISettings(
        enabled=enabled,
        include_in_review=include_in_review,
        embedding_model=embedding_model,
        embedding_dimensions=embedding_dimensions,
        retrieval_top_k=retrieval_top_k,
        rerank_top_n=rerank_top_n,
        chunk_chars=chunk_chars,
        chunk_overlap_chars=chunk_overlap_chars,
        cohere_rerank_model=cohere_rerank_model,
        openai_api_key=openai_api_key,
        cohere_api_key=cohere_api_key,
        turbopuffer_api_key=turbopuffer_api_key,
        turbopuffer_namespace=turbopuffer_namespace,
        turbopuffer_region=turbopuffer_region,
        neo4j_uri=neo4j_uri,
        neo4j_user=neo4j_user,
        neo4j_password=neo4j_password,
        neo4j_database=neo4j_database,
        temporal_coupling_max_commits=temporal_coupling_max_commits,
    )


def provider_status(settings: AISettings) -> dict[str, str]:
    """Return high-level provider readiness map for diagnostics."""
    return {
        "openai_embeddings": "ready" if settings.has_openai else "missing_api_key",
        "cohere_rerank": "ready" if settings.has_cohere else "missing_api_key",
        "turbopuffer": "ready" if settings.has_turbopuffer else "missing_api_key",
        "neo4j": "ready" if settings.has_neo4j else "missing_credentials",
    }


__all__ = ["AISettings", "provider_status", "resolve_ai_settings"]
