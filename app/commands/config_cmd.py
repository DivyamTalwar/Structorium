"""config command: show/set/unset project configuration."""

from __future__ import annotations

import argparse
import sys

from app.commands.helpers.runtime import command_runtime
from core.config import (
    CONFIG_SCHEMA,
    save_config,
    set_config_value,
    unset_config_value,
)
from core.fallbacks import print_error
from core.output_api import colorize


def cmd_config(args: argparse.Namespace) -> None:
    """Handle config subcommands: show, set, unset."""
    action = getattr(args, "config_action", None)
    if action == "set":
        _config_set(args)
    elif action == "unset":
        _config_unset(args)
    else:
        _config_show(args)


def _config_show(args):
    """Print all config keys with current values and descriptions."""
    config = command_runtime(args).config

    print(colorize("\n  Structorium Configuration\n", "bold"))
    for key, schema in CONFIG_SCHEMA.items():
        value = config.get(key, schema.default)
        is_default = value == schema.default

        # Format display value
        if schema.type is int and key.endswith("_days") and value == 0:
            display = "never (0)"
        elif isinstance(value, list):
            display = ", ".join(value) if value else "(empty)"
        elif isinstance(value, dict):
            display = f"{len(value)} entries" if value else "(empty)"
        else:
            display = str(value)

        default_tag = colorize(" (default)", "dim") if is_default else ""
        print(f"  {key:<25} {display}{default_tag}")
        print(colorize(f"  {'':25} {schema.description}", "dim"))
    print()


def _config_set(args):
    """Set a config key to a value."""
    config = command_runtime(args).config
    key = args.config_key
    value = args.config_value

    try:
        set_config_value(config, key, value)
    except (KeyError, ValueError) as e:
        print_error(str(e))
        sys.exit(1)

    try:
        save_config(config)
    except OSError as e:
        print_error(f"could not save config: {e}")
        sys.exit(1)
    display = config[key]
    if isinstance(display, int) and key.endswith("_days") and display == 0:
        display = "never (0)"
    print(colorize(f"  Set {key} = {display}", "green"))


def _config_unset(args):
    """Reset a config key to its default."""
    config = command_runtime(args).config
    key = args.config_key

    try:
        unset_config_value(config, key)
    except KeyError as e:
        print_error(str(e))
        sys.exit(1)

    try:
        save_config(config)
    except OSError as e:
        print_error(f"could not save config: {e}")
        sys.exit(1)
    default = CONFIG_SCHEMA[key].default
    print(colorize(f"  Reset {key} to default ({default})", "green"))
