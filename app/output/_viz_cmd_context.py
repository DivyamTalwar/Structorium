"""CLI context loading helpers for `structorium tree` and `structorium viz`."""

from __future__ import annotations

import json
from pathlib import Path

import state as state_module
from app.commands.helpers.lang import resolve_lang
from app.commands.helpers.runtime import command_runtime
from core.fallbacks import warn_best_effort


def load_cmd_context(args: object) -> tuple[Path, object | None, dict | None]:
    """Load language config and state from CLI args."""
    lang = resolve_lang(args)
    runtime = command_runtime(args)
    state = runtime.state
    if not isinstance(state, dict):
        scan_state_path = runtime.state_path
        try:
            state = state_module.load_state(scan_state_path)
        except (OSError, json.JSONDecodeError) as exc:
            warn_best_effort(
                "Could not load scan state for visualization "
                f"({scan_state_path}, {exc.__class__.__name__}: {exc}); "
                "rendering without finding overlays."
            )
            state = None
    return Path(args.path), lang, state


__all__ = ["load_cmd_context"]
