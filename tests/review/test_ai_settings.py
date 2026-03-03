"""Tests for AI settings resolution."""

from __future__ import annotations

from intelligence.ai.settings import resolve_ai_settings


def test_resolve_ai_settings_defaults_disabled(monkeypatch):
    for key in (
        "STRUCTORIUM_AI_ENABLED",
        "OPENAI_API_KEY",
        "COHERE_API_KEY",
        "TURBOPUFFER_API_KEY",
        "NEO4J_PASSWORD",
    ):
        monkeypatch.delenv(key, raising=False)
    settings = resolve_ai_settings({})
    assert settings.enabled is False
    assert settings.include_in_review is True
    assert settings.embedding_model == "text-embedding-3-large"
    assert settings.embedding_dimensions is None
    assert settings.retrieval_top_k >= 1
    assert settings.rerank_top_n >= 1


def test_resolve_ai_settings_from_config(monkeypatch):
    monkeypatch.delenv("STRUCTORIUM_AI_ENABLED", raising=False)
    settings = resolve_ai_settings(
        {
            "ai_enabled": True,
            "ai_include_in_review": True,
            "ai_embedding_model": "text-embedding-3-small",
            "ai_embedding_dimensions": 256,
            "ai_retrieval_top_k": 7,
            "ai_rerank_top_n": 3,
            "ai_chunk_chars": 1200,
            "ai_chunk_overlap_chars": 100,
            "ai_turbopuffer_namespace": "my-ns",
            "ai_turbopuffer_region": "aws-us-west-2",
            "ai_neo4j_uri": "bolt://db:7687",
            "ai_neo4j_user": "neo4j",
            "ai_neo4j_database": "graph",
        }
    )
    assert settings.enabled is True
    assert settings.embedding_model == "text-embedding-3-small"
    assert settings.embedding_dimensions == 256
    assert settings.retrieval_top_k == 7
    assert settings.rerank_top_n == 3
    assert settings.chunk_chars == 1200
    assert settings.chunk_overlap_chars == 100
    assert settings.turbopuffer_namespace == "my-ns"
    assert settings.turbopuffer_region == "aws-us-west-2"
    assert settings.neo4j_uri == "bolt://db:7687"
    assert settings.neo4j_user == "neo4j"
    assert settings.neo4j_database == "graph"
