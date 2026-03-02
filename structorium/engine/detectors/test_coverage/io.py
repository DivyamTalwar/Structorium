"""Shared file-read contract helpers for test-coverage detection."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from structorium.core.fallbacks import log_best_effort_failure, warn_best_effort

LOGGER = logging.getLogger(__name__)
_WARNED_READ_FAILURES: set[tuple[str, str]] = set()


@dataclass(frozen=True)
class CoverageFileReadResult:
    """Typed file-read outcome for test-coverage heuristics/metrics."""

    ok: bool
    content: str
    error_kind: str | None = None
    error_message: str | None = None


def read_coverage_file(
    filepath: str,
    *,
    context: str,
) -> CoverageFileReadResult:
    """Read a source file and emit one best-effort warning per context/path."""
    try:
        return CoverageFileReadResult(ok=True, content=Path(filepath).read_text())
    except (OSError, UnicodeDecodeError) as exc:
        log_best_effort_failure(LOGGER, f"{context} read {filepath}", exc)
        dedupe_key = (context, filepath)
        if dedupe_key not in _WARNED_READ_FAILURES:
            _WARNED_READ_FAILURES.add(dedupe_key)
            warn_best_effort(
                f"Could not read file for test coverage ({context}): {filepath} "
                f"[{exc.__class__.__name__}]"
            )
        return CoverageFileReadResult(
            ok=False,
            content="",
            error_kind=exc.__class__.__name__,
            error_message=str(exc),
        )


def clear_coverage_read_warning_cache_for_tests() -> None:
    """Test helper to reset warning de-duplication state."""
    _WARNED_READ_FAILURES.clear()


__all__ = [
    "CoverageFileReadResult",
    "clear_coverage_read_warning_cache_for_tests",
    "read_coverage_file",
]
