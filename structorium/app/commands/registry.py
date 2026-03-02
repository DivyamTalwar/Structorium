"""Central command registry for CLI command handler resolution."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

CommandHandler = Callable[[Any], None]

_COMMAND_HANDLERS: dict[str, CommandHandler] | None = None


def _build_handlers() -> dict[str, CommandHandler]:
    """Import all command modules and build the handler dict on first access."""
    from structorium.app.commands.config_cmd import cmd_config
    from structorium.app.commands.detect import cmd_detect
    from structorium.app.commands.dev_cmd import cmd_dev
    from structorium.app.commands.exclude_cmd import cmd_exclude
    from structorium.app.commands.fix import cmd_fix
    from structorium.app.commands.langs import cmd_langs
    from structorium.app.commands.move import cmd_move
    from structorium.app.commands.next import cmd_next
    from structorium.app.commands.plan import cmd_plan
    from structorium.app.commands.resolve import cmd_ignore_pattern
    from structorium.app.commands.review import cmd_review
    from structorium.app.commands.scan import cmd_scan
    from structorium.app.commands.show import cmd_show
    from structorium.app.commands.status_cmd import cmd_status
    from structorium.app.commands.update_skill import cmd_update_skill
    from structorium.app.commands.viz_cmd import cmd_tree, cmd_viz
    from structorium.app.commands.zone_cmd import cmd_zone

    return {
        "scan": cmd_scan,
        "status": cmd_status,
        "show": cmd_show,
        "next": cmd_next,
        "ignore": cmd_ignore_pattern,
        "exclude": cmd_exclude,
        "fix": cmd_fix,
        "plan": cmd_plan,
        "detect": cmd_detect,
        "tree": cmd_tree,
        "viz": cmd_viz,
        "move": cmd_move,
        "zone": cmd_zone,
        "review": cmd_review,
        "config": cmd_config,
        "dev": cmd_dev,
        "langs": cmd_langs,
        "update-skill": cmd_update_skill,
    }


def get_command_handlers() -> dict[str, CommandHandler]:
    """Return cached command handler dict, building on first access."""
    global _COMMAND_HANDLERS
    if _COMMAND_HANDLERS is None:
        _COMMAND_HANDLERS = _build_handlers()
    return _COMMAND_HANDLERS


__all__ = ["CommandHandler", "get_command_handlers"]
