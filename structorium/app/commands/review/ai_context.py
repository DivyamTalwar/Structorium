"""AI context enrichment for holistic review packets."""

from __future__ import annotations

from pathlib import Path

from structorium.core.output_api import colorize, log
from structorium.intelligence.ai import build_ai_review_context, resolve_ai_settings


def enrich_holistic_packet_with_ai_context(
    *,
    packet: dict[str, object],
    repo_root: Path,
    lang: object,
    files: list[str] | None,
    config: dict | None,
) -> None:
    """Best-effort AI context injection for holistic review packets."""
    settings = resolve_ai_settings(config)
    if not settings.enabled or not settings.include_in_review:
        return

    selected_files = (
        files
        if isinstance(files, list)
        else (
            lang.file_finder(repo_root)
            if getattr(lang, "file_finder", None)
            else []
        )
    )
    query_text = _query_from_packet(packet)
    try:
        ai_context = build_ai_review_context(
            repo_root=repo_root,
            lang=lang,
            files=selected_files or [],
            settings=settings,
            query_text=query_text,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        packet["ai_context"] = {
            "enabled": True,
            "status": "error",
            "error": str(exc),
        }
        log(colorize(f"  AI context enrichment failed: {exc}", "yellow"))
        return

    packet["ai_context"] = ai_context
    _attach_batch_ai_hints(packet, ai_context)

    status = str(ai_context.get("status", "unknown"))
    if status == "ready":
        hits = (
            (ai_context.get("vector") or {}).get("top_hits", [])
            if isinstance(ai_context.get("vector"), dict)
            else []
        )
        hit_count = len(hits) if isinstance(hits, list) else 0
        log(colorize(f"  AI context ready: {hit_count} reranked retrieval hits", "dim"))
    else:
        log(colorize(f"  AI context status: {status}", "yellow"))


def _query_from_packet(packet: dict[str, object]) -> str:
    dims = packet.get("dimensions", [])
    if isinstance(dims, list):
        dim_text = ", ".join(str(dim) for dim in dims[:20] if isinstance(dim, str))
    else:
        dim_text = ""
    base = "Find architecture risks, coupling hotspots, and contract/test gaps."
    if dim_text:
        return f"{base} Prioritize dimensions: {dim_text}."
    return base


def _attach_batch_ai_hints(packet: dict[str, object], ai_context: dict[str, object]) -> None:
    vector_section = ai_context.get("vector")
    if not isinstance(vector_section, dict):
        return
    top_hits = vector_section.get("top_hits", [])
    if not isinstance(top_hits, list):
        return
    ranked_files: list[str] = []
    seen: set[str] = set()
    for item in top_hits:
        if not isinstance(item, dict):
            continue
        path = item.get("file")
        if not isinstance(path, str) or not path:
            continue
        if path in seen:
            continue
        seen.add(path)
        ranked_files.append(path)
        if len(ranked_files) >= 8:
            break
    if not ranked_files:
        return

    batches = packet.get("investigation_batches", [])
    if not isinstance(batches, list):
        return
    for batch in batches:
        if not isinstance(batch, dict):
            continue
        files_to_read = batch.get("files_to_read", [])
        existing = set(files_to_read) if isinstance(files_to_read, list) else set()
        hints = [path for path in ranked_files if path not in existing][:3]
        if hints:
            batch["ai_seed_files"] = hints


__all__ = ["enrich_holistic_packet_with_ai_context"]
