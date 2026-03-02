"""Large file detection (LOC threshold)."""

import logging

from pathlib import Path

from structorium.core.file_paths import resolve_scan_file
from structorium.core.fallbacks import log_best_effort_failure

logger = logging.getLogger(__name__)


def detect_large_files(
    path: Path, file_finder, threshold: int = 500
) -> tuple[list[dict], int]:
    """Find files exceeding a line count threshold."""
    files = file_finder(path)
    entries = []
    for filepath in files:
        try:
            p = resolve_scan_file(filepath, scan_root=path)
            loc = len(p.read_text().splitlines())
            if loc > threshold:
                entries.append({"file": filepath, "loc": loc})
        except (OSError, UnicodeDecodeError) as exc:
            log_best_effort_failure(
                logger,
                f"read large-file detector candidate {filepath}",
                exc,
            )
            continue
    return sorted(entries, key=lambda e: -e["loc"]), len(files)
