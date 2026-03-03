"""Shared regex policies for migration/auth signal detection."""

from __future__ import annotations

import re

DEPRECATION_MARKER_RE = re.compile(r"@[Dd]eprecated\b|DEPRECATED", re.MULTILINE)

MIGRATION_TODO_RE = re.compile(
    r"(?:TODO|FIXME|HACK)\b(?:\s*:)?[^\n]*\b(?:migrat\w*|legacy|deprecat\w*|old.?api|remove.?after)\b",
    re.IGNORECASE,
)

SERVICE_ROLE_TOKEN_RE = re.compile(
    r"\b(?:service[_-]?role(?:_key)?|serviceRole(?:Key)?|SUPABASE_SERVICE_ROLE(?:_KEY)?)\b",
    re.IGNORECASE,
)

SERVER_ONLY_PATH_HINTS = (
    "/api/",
    "/server/",
    "/backend/",
    "/functions/",
    "/supabase/functions/",
    "/scripts/",
)


def is_server_only_path(path: str) -> bool:
    """Best-effort classification for server-only source paths."""
    if not path:
        return False
    normalized = path.replace("\\", "/")
    prefixed = normalized if normalized.startswith("/") else f"/{normalized}"
    return any(hint in prefixed for hint in SERVER_ONLY_PATH_HINTS)
