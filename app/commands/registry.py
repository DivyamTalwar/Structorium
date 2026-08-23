"""Central command registry for CLI command handler resolution."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

CommandHandler = Callable[[Any], None]

_COMMAND_HANDLERS: dict[str, CommandHandler] | None = None


def _build_handlers() -> dict[str, CommandHandler]:
    """Import all command modules and build the handler dict on first access."""
    from app.commands.config_cmd import cmd_config
    from app.commands.detect import cmd_detect
    from app.commands.dev_cmd import cmd_dev
    from app.commands.exclude_cmd import cmd_exclude
    from app.commands.fix import cmd_fix
    from app.commands.impact_cmd import cmd_impact
    from app.commands.langs import cmd_langs
    from app.commands.move import cmd_move
    from app.commands.next import cmd_next
    from app.commands.plan import cmd_plan
    from app.commands.resolve import cmd_ignore_pattern
    from app.commands.review import cmd_review
    from app.commands.scan import cmd_scan
    from app.commands.show import cmd_show
    from app.commands.status_cmd import cmd_status
    from app.commands.update_skill import cmd_update_skill
    from app.commands.viz_cmd import cmd_tree, cmd_viz
    from app.commands.zone_cmd import cmd_zone

    return {
        "scan": cmd_scan,
        "status": cmd_status,
        "show": cmd_show,
        "next": cmd_next,
        "ignore": cmd_ignore_pattern,
        "exclude": cmd_exclude,
        "fix": cmd_fix,
        "impact": cmd_impact,
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
