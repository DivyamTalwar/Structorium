"""Cohere reranking with lexical fallback."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from .http import RetryPolicy, post_json
from .settings import AISettings

COHERE_RERANK_URL = "https://api.cohere.com/v2/rerank"
_TOKEN_RE = re.compile(r"[a-z0-9_]{2,}")


@dataclass(frozen=True)
class RerankResult:
    index: int
    relevance_score: float


def _token_overlap_score(query: str, text: str) -> float:
    q_tokens = _TOKEN_RE.findall(query.lower())
    t_tokens = _TOKEN_RE.findall(text.lower())
    if not q_tokens or not t_tokens:
        return 0.0
    q_counts = Counter(q_tokens)
    t_counts = Counter(t_tokens)
    numer = sum(min(q_counts[t], t_counts[t]) for t in q_counts)
    denom = max(sum(q_counts.values()), 1)
    return float(numer) / float(denom)


def _lexical_rerank(query: str, documents: list[str], top_n: int) -> list[RerankResult]:
    scored = [
        RerankResult(index=i, relevance_score=_token_overlap_score(query, doc))
        for i, doc in enumerate(documents)
    ]
    scored.sort(key=lambda item: item.relevance_score, reverse=True)
    return scored[:top_n]


def rerank_documents(
    *,
    query: str,
    documents: list[str],
    settings: AISettings,
    top_n: int | None = None,
    retry: RetryPolicy | None = None,
) -> list[RerankResult]:
    """Rerank documents using Cohere; fallback to lexical ranking."""
    if not documents:
        return []
    keep = max(1, top_n or settings.rerank_top_n)

    if not settings.cohere_api_key:
        return _lexical_rerank(query, documents, keep)

    payload = {
        "model": settings.cohere_rerank_model,
        "query": query,
        "documents": documents,
        "top_n": keep,
    }
    try:
        response = post_json(
            url=COHERE_RERANK_URL,
            payload=payload,
            headers={
                "Authorization": f"Bearer {settings.cohere_api_key}",
            },
            retry=retry,
        )
    except Exception:
        return _lexical_rerank(query, documents, keep)

    results_raw = response.get("results", [])
    if not isinstance(results_raw, list):
        return _lexical_rerank(query, documents, keep)

    out: list[RerankResult] = []
    for item in results_raw:
        if not isinstance(item, dict):
            continue
        idx = item.get("index")
        score = item.get("relevance_score")
        if not isinstance(idx, int | float) or not isinstance(score, int | float):
            continue
        out.append(RerankResult(index=int(idx), relevance_score=float(score)))
    if not out:
        return _lexical_rerank(query, documents, keep)
    out.sort(key=lambda row: row.relevance_score, reverse=True)
    return out[:keep]


__all__ = ["COHERE_RERANK_URL", "RerankResult", "rerank_documents"]
