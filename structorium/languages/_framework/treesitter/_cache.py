"""Scan-scoped tree-sitter parse tree cache."""

from __future__ import annotations

from pathlib import Path


class ParseTreeCache:
    """Cache parsed tree-sitter trees during a scan.

    Key: (filepath, grammar_name) -> (source_bytes, parsed_tree)
    Stores source_bytes so callers can use them without re-reading.
    """

    def __init__(self) -> None:
        self._enabled: bool = False
        self._trees: dict[tuple[str, str], tuple[bytes, object]] = {}

    def enable(self) -> None:
        self._enabled = True
        self._trees = {}

    def disable(self) -> None:
        self._enabled = False
        self._trees = {}

    def get_or_parse(
        self, filepath: str, parser, grammar: str
    ) -> tuple[bytes, object] | None:
        """Read file and parse, returning (source_bytes, tree). Uses cache if enabled."""
        key = (filepath, grammar)
        if self._enabled and key in self._trees:
            return self._trees[key]

        try:
            source = Path(filepath).read_bytes()
        except (OSError, UnicodeDecodeError):
            return None

        tree = parser.parse(source)
        if self._enabled:
            self._trees[key] = (source, tree)
        return source, tree


_PARSE_CACHE = ParseTreeCache()


def enable_parse_cache() -> None:
    """Enable scan-scoped parse tree cache."""
    _PARSE_CACHE.enable()


def disable_parse_cache() -> None:
    """Disable parse tree cache and free memory."""
    _PARSE_CACHE.disable()


def is_parse_cache_enabled() -> bool:
    """Check if parse cache is currently enabled."""
    return _PARSE_CACHE._enabled


__all__ = [
    "ParseTreeCache",
    "disable_parse_cache",
    "enable_parse_cache",
    "is_parse_cache_enabled",
]
