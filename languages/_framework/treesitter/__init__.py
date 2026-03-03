"""Tree-sitter integration — optional, gracefully degrades when not installed.

Install with: pip install tree-sitter-language-pack
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_AVAILABLE = False
try:
    import tree_sitter_language_pack  # noqa: F401

    _AVAILABLE = True
except ImportError:
    logger.debug("tree-sitter-language-pack not installed; tree-sitter features disabled")


def is_available() -> bool:
    """Return True if tree-sitter-language-pack is installed."""
    return _AVAILABLE


def enable_parse_cache() -> None:
    """Enable scan-scoped parse tree cache."""
    from ._cache import enable_parse_cache as _enable

    _enable()


def disable_parse_cache() -> None:
    """Disable parse tree cache and free memory."""
    from ._cache import disable_parse_cache as _disable

    _disable()


def is_parse_cache_enabled() -> bool:
    """Check if parse cache is currently enabled."""
    from ._cache import is_parse_cache_enabled as _is_enabled

    return _is_enabled()


def get_spec(language: str) -> TreeSitterLangSpec | None:
    """Return tree-sitter spec for a language key, if configured."""
    key = str(language or "").strip().lower()
    if not key:
        return None
    from ._specs import TREESITTER_SPECS

    return TREESITTER_SPECS.get(key)


def list_specs() -> dict[str, TreeSitterLangSpec]:
    """Return a shallow copy of the public tree-sitter spec registry."""
    from ._specs import TREESITTER_SPECS

    return dict(TREESITTER_SPECS)


@dataclass(frozen=True)
class TreeSitterLangSpec:
    """Per-language tree-sitter configuration.

    Fields:
        grammar: tree-sitter grammar name (e.g. "go", "rust")
        function_query: S-expression query capturing @func, @name, @body
        comment_node_types: AST node types considered comments
        string_node_types: AST node types considered strings (for normalization)
        import_query: S-expression query capturing @import and @path
        resolve_import: (import_text, source_file, scan_path) -> abs_path | None
        class_query: S-expression query capturing @class, @name, @body
        log_patterns: regexes for log/debug lines to strip during normalization
    """

    grammar: str
    function_query: str
    comment_node_types: frozenset[str]
    string_node_types: frozenset[str] = frozenset()

    import_query: str = ""
    resolve_import: Callable[[str, str, str], str | None] | None = None

    class_query: str = ""

    log_patterns: tuple[str, ...] = (
        r"^\s*(?:fmt\.Print|log\.)",
        r"^\s*(?:println!|eprintln!|dbg!)",
        r"^\s*(?:puts |p |pp )",
        r"^\s*(?:print\(|NSLog)",
        r"^\s*(?:System\.out\.|Logger\.)",
        r"^\s*console\.",
    )


# Common exception tuple for tree-sitter parser/query initialisation failures.
# Used across all treesitter modules to avoid repeating the same 4-tuple.
PARSE_INIT_ERRORS: tuple[type[Exception], ...] = (
    ImportError, OSError, ValueError, RuntimeError
)

__all__ = [
    "PARSE_INIT_ERRORS",
    "TreeSitterLangSpec",
    "disable_parse_cache",
    "enable_parse_cache",
    "get_spec",
    "is_available",
    "is_parse_cache_enabled",
    "list_specs",
]

# Re-export phase factories for convenience.
# Actual definitions live in .phases to avoid circular imports at import time.
def __getattr__(name: str):  # noqa: N807
    _PHASE_EXPORTS = {
        "all_treesitter_phases",
        "make_ast_smells_phase",
        "make_cohesion_phase",
        "make_unused_imports_phase",
    }
    if name in _PHASE_EXPORTS:
        from languages._framework.treesitter import phases as phases_mod

        return getattr(phases_mod, name)
    if name == "TREESITTER_SPECS" or name.endswith("_SPEC"):
        from languages._framework.treesitter import _specs as specs_mod

        if hasattr(specs_mod, name):
            return getattr(specs_mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
