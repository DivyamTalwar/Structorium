"""OpenAI embedding client for Structorium AI context."""

from __future__ import annotations

from collections.abc import Iterable

from .http import RetryPolicy, post_json
from .settings import AISettings

OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"
_MAX_BATCH_SIZE = 96


def embed_texts(
    texts: Iterable[str],
    *,
    settings: AISettings,
    retry: RetryPolicy | None = None,
) -> list[list[float]]:
    """Embed text inputs with OpenAI `/v1/embeddings`."""
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required for embeddings")

    normalized = [text for text in texts if isinstance(text, str) and text.strip()]
    if not normalized:
        return []

    all_vectors: list[list[float]] = []
    for i in range(0, len(normalized), _MAX_BATCH_SIZE):
        batch = normalized[i : i + _MAX_BATCH_SIZE]
        payload: dict[str, object] = {
            "model": settings.embedding_model,
            "input": batch,
            "encoding_format": "float",
        }
        if settings.embedding_dimensions is not None:
            payload["dimensions"] = settings.embedding_dimensions

        response = post_json(
            url=OPENAI_EMBEDDINGS_URL,
            payload=payload,
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            retry=retry,
        )
        raw_data = response.get("data", [])
        if not isinstance(raw_data, list):
            raise ValueError("OpenAI embeddings response missing `data` list")

        vectors: list[list[float]] = []
        for item in raw_data:
            if not isinstance(item, dict):
                continue
            emb = item.get("embedding")
            if isinstance(emb, list):
                vectors.append([float(v) for v in emb if isinstance(v, int | float)])
        if len(vectors) != len(batch):
            raise ValueError(
                "OpenAI embeddings response count mismatch "
                f"(expected {len(batch)}, got {len(vectors)})"
            )
        all_vectors.extend(vectors)

    return all_vectors


def embed_query(
    query: str,
    *,
    settings: AISettings,
    retry: RetryPolicy | None = None,
) -> list[float]:
    """Embed one search query."""
    vectors = embed_texts([query], settings=settings, retry=retry)
    return vectors[0] if vectors else []


__all__ = ["OPENAI_EMBEDDINGS_URL", "embed_query", "embed_texts"]
