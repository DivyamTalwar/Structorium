"""Move helpers for language plugin scaffolding."""

from __future__ import annotations

from languages._framework.commands_base import (
    scaffold_find_replacements as find_replacements,
)
from languages._framework.commands_base import (
    scaffold_find_self_replacements as find_self_replacements,
)
from languages._framework.commands_base import (
    scaffold_verify_hint as get_verify_hint,
)


__all__ = ["find_replacements", "find_self_replacements", "get_verify_hint"]
