"""Target-score normalization helpers for command modules."""

from __future__ import annotations

from structorium.core._internal.text_utils import is_numeric


def coerce_target_score(value: object, *, fallback: float = 95.0) -> float:
    """Normalize target score-like values to a safe [0, 100] float."""
    if is_numeric(fallback):
        fallback_value = float(fallback)
    else:
        fallback_value = 95.0

    if is_numeric(value):
        parsed = float(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            parsed = fallback_value
        else:
            try:
                parsed = float(text)
            except ValueError:
                parsed = fallback_value
    else:
        parsed = fallback_value
    return max(0.0, min(100.0, parsed))


def target_strict_score_from_config(
    config: dict | None, *, fallback: float = 95.0
) -> float:
    """Read and normalize target strict score from config."""
    if isinstance(config, dict):
        raw = config.get("target_strict_score", fallback)
    else:
        raw = fallback
    return coerce_target_score(raw, fallback=fallback)

