"""Planning public API with lazy imports to avoid import cycles."""

from __future__ import annotations

from typing import Any

from structorium.engine.planning.common import CONFIDENCE_ORDER, TIER_LABELS


def generate_plan_md(*args: Any, **kwargs: Any):
    from structorium.engine.planning.core import generate_plan_md as _generate_plan_md

    return _generate_plan_md(*args, **kwargs)


def generate_findings(*args: Any, **kwargs: Any):
    from structorium.engine.planning.core import generate_findings as _generate_findings

    return _generate_findings(*args, **kwargs)


def get_next_item(*args: Any, **kwargs: Any):
    from structorium.engine.planning.core import get_next_item as _get_next_item

    return _get_next_item(*args, **kwargs)


def get_next_items(*args: Any, **kwargs: Any):
    from structorium.engine.planning.core import get_next_items as _get_next_items

    return _get_next_items(*args, **kwargs)


__all__ = [
    "CONFIDENCE_ORDER",
    "TIER_LABELS",
    "generate_findings",
    "generate_plan_md",
    "get_next_item",
    "get_next_items",
]
