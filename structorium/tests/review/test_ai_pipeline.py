"""Tests for AI pipeline orchestration fallbacks."""

from __future__ import annotations

from types import SimpleNamespace

from structorium.intelligence.ai.pipeline import build_ai_review_context
from structorium.intelligence.ai.settings import AISettings


def _settings_enabled_no_keys() -> AISettings:
    return AISettings(
        enabled=True,
        include_in_review=True,
        embedding_model="text-embedding-3-large",
        embedding_dimensions=None,
        retrieval_top_k=10,
        rerank_top_n=5,
        chunk_chars=800,
        chunk_overlap_chars=80,
        cohere_rerank_model="rerank-v3.5",
        openai_api_key=None,
        cohere_api_key=None,
        turbopuffer_api_key=None,
        turbopuffer_namespace="structorium-code",
        turbopuffer_region=None,
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password=None,
        neo4j_database="neo4j",
    )


def test_build_ai_review_context_reports_missing_credentials(tmp_path):
    source = tmp_path / "src" / "main.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("def run():\n    return 1\n")

    lang = SimpleNamespace(dep_graph={str(source): {"imports": set()}})
    ctx = build_ai_review_context(
        repo_root=tmp_path,
        lang=lang,
        files=[str(source)],
        settings=_settings_enabled_no_keys(),
        query_text="find contracts and tests",
    )

    assert ctx["enabled"] is True
    assert ctx["status"] == "error"
    assert isinstance(ctx["provider_status"], dict)
    assert ctx["provider_status"]["openai_embeddings"] == "missing_api_key"
    assert ctx["provider_status"]["turbopuffer"] == "missing_api_key"
    assert ctx["provider_status"]["neo4j"] == "missing_credentials"
