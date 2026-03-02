"""Runtime context helpers for command handlers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from structorium import state as state_mod
from structorium.app.commands.helpers.state import state_path
from structorium.core.config import load_config


@dataclass(frozen=True)
class CommandRuntime:
    """Explicit runtime dependencies shared by command handlers."""

    config: dict[str, Any]
    state: dict[str, Any]
    state_path: Path | None


def command_runtime(args) -> CommandRuntime:
    """Return runtime context from explicit args.runtime or construct one."""
    runtime = getattr(args, "runtime", None)
    if isinstance(runtime, CommandRuntime):
        return runtime

    config = load_config()
    state_file = state_path(args)
    if isinstance(state_file, str):
        state_file = Path(state_file)

    state = state_mod.load_state(state_file)

    return CommandRuntime(config=config, state=state, state_path=state_file)


__all__ = ["CommandRuntime", "command_runtime"]
