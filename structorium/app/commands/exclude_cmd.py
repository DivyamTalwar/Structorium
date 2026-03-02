"""exclude command: add path patterns to the config exclude list."""

from __future__ import annotations

import argparse
import sys

from structorium.core import config as config_mod
from structorium.core.fallbacks import print_error
from structorium.core.output_api import colorize
from structorium.core.tooling import check_config_staleness


def cmd_exclude(args: argparse.Namespace) -> None:
    """Add a path pattern to the exclude list."""
    config = config_mod.load_config()
    config_mod.add_exclude_pattern(config, args.pattern)
    config["needs_rescan"] = True
    try:
        config_mod.save_config(config)
    except OSError as exc:
        print_error(f"could not save config: {exc}")
        sys.exit(1)

    print(colorize(f"Added exclude pattern: {args.pattern}", "green"))
    config_warning = check_config_staleness(config)
    if config_warning:
        print(colorize(f"  {config_warning}", "yellow"))


__all__ = ["cmd_exclude"]
