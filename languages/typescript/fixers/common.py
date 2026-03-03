"""Compatibility re-export shim for legacy TypeScript fixer helper imports."""

from __future__ import annotations

from .fixer_io import apply_fixer
from .import_rewrite import (
    _collect_import_statement,
    process_unused_import_lines,
    remove_symbols_from_import_stmt,
)
from .syntax_scan import (
    collapse_blank_lines,
    extract_body_between_braces,
    find_balanced_end,
)

__all__ = [
    "_collect_import_statement",
    "apply_fixer",
    "collapse_blank_lines",
    "extract_body_between_braces",
    "find_balanced_end",
    "process_unused_import_lines",
    "remove_symbols_from_import_stmt",
]
