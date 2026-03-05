"""End-to-end indexing + retrieval orchestration for AI review context."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from core.discovery_api import read_file_text, rel

from .embeddings import embed_query, embed_texts
from .incremental_memory import build_incremental_review_memory
from .neo4j_store import GraphNeighbors, Neo4jStore, Neo4jUnavailableError
from .rerank import rerank_documents
from .settings import AISettings, provider_status
from .turbopuffer_store import TurbopufferStore, TurbopufferUnavailableError, VectorHit


@dataclass(frozen=True)
class Chunk:
    row_id: str
    file: str
    chunk_index: int
    content: str
    loc: int
    sha1: str


def build_ai_review_context(
    *,
    repo_root: Path,
    lang: object,
    files: list[str],
    settings: AISettings,
    query_text: str,
) -> dict[str, object]:
    """Build AI context packet section for review workflows."""
    status = provider_status(settings)
    context: dict[str, object] = {
        "enabled": settings.enabled,
        "provider_status": status,
    }
    if not settings.enabled:
        context["status"] = "disabled"
        return context
    if not files:
        context["status"] = "no_files"
        return context

    chunks = _build_chunks(files, settings=settings)
    context["index_summary"] = {
        "files_indexed": len({chunk.file for chunk in chunks}),
        "chunks_indexed": len(chunks),
    }
    if not chunks:
        context["status"] = "no_chunks"
        return context

    # 1) Vector index: upsert chunks
    vector_index_ok = False
    vector_error = ""
    hits: list[VectorHit] = []
    if settings.has_openai and settings.has_turbopuffer:
        try:
            vectors = embed_texts(
                [chunk.content for chunk in chunks],
                settings=settings,
            )
            rows = _rows_from_chunks(chunks, vectors)
            store = TurbopufferStore(settings)
            store.upsert(rows)
            query_vec = embed_query(query_text, settings=settings)
            hits = store.query(query_vec, top_k=settings.retrieval_top_k)
            vector_index_ok = True
        except (ValueError, TurbopufferUnavailableError, RuntimeError) as exc:
            vector_error = str(exc)
    else:
        vector_error = "missing_openai_or_turbopuffer_credentials"

    # 2) Graph index: upsert dep graph and fetch neighbors
    graph_ok = False
    graph_error = ""
    neighbors: list[GraphNeighbors] = []
    if settings.has_neo4j:
        graph_store = None
        try:
            graph_store = Neo4jStore(settings)
            graph_files, graph_edges = _collect_graph_payload(
                chunks=chunks,
                dep_graph=getattr(lang, "dep_graph", None),
                repo_root=repo_root,
            )
            graph_store.upsert_graph(
                files=graph_files,
                edges=graph_edges,
                run_id=_run_id(chunks),
            )
            neighbor_paths = _top_hit_paths(hits, max_paths=10) or [
                rel(path) for path in files[:10]
            ]
            neighbors = graph_store.neighbors(neighbor_paths, limit=8)
            graph_ok = True
        except (Neo4jUnavailableError, RuntimeError, ValueError) as exc:
            graph_error = str(exc)
        finally:
            if graph_store is not None:
                graph_store.close()
    else:
        graph_error = "missing_neo4j_credentials"

    # 3) Rerank vector hits (or lexical fallback if Cohere key missing)
    reranked = _rerank_hits(query_text, hits, settings=settings)

    context["status"] = "ready" if (vector_index_ok or graph_ok) else "error"
    context["vector"] = {
        "ok": vector_index_ok,
        "error": vector_error,
        "hit_count": len(hits),
        "top_hits": reranked,
    }
    context["graph"] = {
        "ok": graph_ok,
        "error": graph_error,
        "neighbors": [
            {
                "path": item.path,
                "fan_in": item.fan_in,
                "fan_out": item.fan_out,
                "imports": item.imports,
                "importers": item.importers,
            }
            for item in neighbors
        ],
    }
    focus_paths = _top_hit_paths(hits, max_paths=14) or [
        chunk.file for chunk in chunks[:14]
    ]
    context["incremental_review"] = build_incremental_review_memory(
        repo_root=repo_root,
        focus_files=focus_paths,
        max_feedback_entries=settings.incremental_review_max_entries,
        max_commits=240,
    )
    context["query"] = query_text
    return context


def _build_chunks(files: list[str], *, settings: AISettings) -> list[Chunk]:
    chunks: list[Chunk] = []
    for filepath in files:
        text = read_file_text(Path(filepath))
        if not text:
            continue
        normalized_path = rel(filepath)
        line_count = len(text.splitlines())
        digest = hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()  # noqa: S324
        for chunk_index, content in enumerate(
            _chunk_text(
                text,
                chunk_chars=settings.chunk_chars,
                overlap_chars=settings.chunk_overlap_chars,
            )
        ):
            row_id = _chunk_id(normalized_path, chunk_index, digest)
            chunks.append(
                Chunk(
                    row_id=row_id,
                    file=normalized_path,
                    chunk_index=chunk_index,
                    content=content,
                    loc=line_count,
                    sha1=digest,
                )
            )
    return chunks


def _chunk_text(text: str, *, chunk_chars: int, overlap_chars: int) -> list[str]:
    if len(text) <= chunk_chars:
        return [text]
    out: list[str] = []
    step = max(1, chunk_chars - overlap_chars)
    start = 0
    total = len(text)
    while start < total:
        end = min(total, start + chunk_chars)
        out.append(text[start:end])
        if end >= total:
            break
        start += step
    return out


def _chunk_id(path: str, chunk_index: int, digest: str) -> str:
    seed = f"{path}::{chunk_index}::{digest}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()  # noqa: S324


def _rows_from_chunks(
    chunks: list[Chunk],
    vectors: list[list[float]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for chunk, vector in zip(chunks, vectors, strict=False):
        rows.append(
            {
                "id": chunk.row_id,
                "vector": vector,
                "file": chunk.file,
                "chunk_index": chunk.chunk_index,
                "content": chunk.content,
                "loc": chunk.loc,
                "sha1": chunk.sha1,
            }
        )
    return rows


def _collect_graph_payload(
    *,
    chunks: list[Chunk],
    dep_graph: object,
    repo_root: Path,
) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
    files_by_path: dict[str, Chunk] = {}
    for chunk in chunks:
        if chunk.file not in files_by_path:
            files_by_path[chunk.file] = chunk

    graph_files = [
        {
            "path": file_path,
            "loc": chunk.loc,
            "sha1": chunk.sha1,
            "language": repo_root.suffix or "codebase",
        }
        for file_path, chunk in files_by_path.items()
    ]

    if not isinstance(dep_graph, dict):
        return graph_files, []

    known = set(files_by_path)
    edges: list[dict[str, str]] = []
    for source, entry in dep_graph.items():
        if not isinstance(entry, dict):
            continue
        source_rel = rel(source)
        if source_rel not in known:
            continue
        imports = entry.get("imports", set())
        if not isinstance(imports, set | list | tuple):
            continue
        for target in imports:
            target_rel = rel(target)
            if target_rel not in known:
                continue
            edges.append({"source": source_rel, "target": target_rel})
    return graph_files, edges


def _top_hit_paths(hits: list[VectorHit], *, max_paths: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for hit in hits:
        raw = hit.attributes.get("file")
        if not isinstance(raw, str):
            continue
        if raw in seen:
            continue
        seen.add(raw)
        out.append(raw)
        if len(out) >= max_paths:
            break
    return out


def _rerank_hits(
    query_text: str,
    hits: list[VectorHit],
    *,
    settings: AISettings,
) -> list[dict[str, object]]:
    if not hits:
        return []
    docs: list[str] = []
    for hit in hits:
        file_path = str(hit.attributes.get("file", ""))
        content = str(hit.attributes.get("content", ""))
        docs.append(f"{file_path}\n{content}")

    ranked = rerank_documents(
        query=query_text,
        documents=docs,
        settings=settings,
        top_n=min(settings.rerank_top_n, len(docs)),
    )

    out: list[dict[str, object]] = []
    for rank, item in enumerate(ranked, start=1):
        if item.index < 0 or item.index >= len(hits):
            continue
        hit = hits[item.index]
        out.append(
            {
                "rank": rank,
                "row_id": hit.row_id,
                "file": hit.attributes.get("file"),
                "chunk_index": hit.attributes.get("chunk_index"),
                "score": round(float(item.relevance_score), 5),
                "vector_score": round(float(hit.score), 5),
                "snippet": _snippet(str(hit.attributes.get("content", ""))),
            }
        )
    return out


def _snippet(text: str, *, limit: int = 280) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit].rstrip()}..."


def _run_id(chunks: list[Chunk]) -> str:
    if not chunks:
        return "empty"
    digest = hashlib.sha1(  # noqa: S324
        "|".join(chunk.sha1 for chunk in chunks[:64]).encode("utf-8")
    ).hexdigest()
    return digest[:16]


__all__ = ["build_ai_review_context"]
