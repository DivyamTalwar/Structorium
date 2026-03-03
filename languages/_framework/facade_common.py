"""Shared helpers for language-specific re-export facade detectors."""

from __future__ import annotations

from collections.abc import Callable


def detect_reexport_facades_common(
    graph: dict,
    *,
    is_facade_fn: Callable[[str], dict | None],
    max_importers: int = 2,
) -> tuple[list[dict], int]:
    """Collect file-level re-export facades using a language detector callback."""
    entries: list[dict] = []
    total_checked = 0

    for filepath, node in graph.items():
        total_checked += 1
        importer_count = node.get("importer_count", 0)
        if importer_count > max_importers:
            continue

        result = is_facade_fn(filepath)
        if not result:
            continue

        entries.append(
            {
                "file": filepath,
                "loc": result["loc"],
                "importers": importer_count,
                "imports_from": result["imports_from"],
                "kind": "file",
            }
        )

    return entries, total_checked


__all__ = ["detect_reexport_facades_common"]
