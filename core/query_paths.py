"""Runtime query payload path helpers."""

from __future__ import annotations

from pathlib import Path

from core._internal.text_utils import get_project_root
from core.runtime_state import current_runtime_context


def query_file_path() -> Path:
    """Return the active query payload file path."""
    runtime = current_runtime_context()
    if isinstance(runtime.query_file, Path):
        return runtime.query_file
    return get_project_root() / ".structorium" / "query.json"


def set_query_file(path: Path | str | None) -> None:
    """Set runtime query path override (primarily for tests)."""
    runtime = current_runtime_context()
    runtime.query_file = Path(path).resolve() if path is not None else None


__all__ = ["query_file_path", "set_query_file"]
