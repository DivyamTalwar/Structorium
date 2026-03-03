"""zone command: show/set/clear zone classifications."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.commands.helpers.lang import resolve_lang
from app.commands.helpers.rendering import print_agent_plan
from app.commands.helpers.runtime import command_runtime
from app.commands.helpers.state import state_path
from core import config as config_mod
from core.fallbacks import print_error
from engine.policy.zones import FileZoneMap, Zone
from core.discovery_api import rel
from core.output_api import colorize


def cmd_zone(args: argparse.Namespace) -> None:
    """Handle zone subcommands: show, set, clear."""
    action = getattr(args, "zone_action", None)
    if action in (None, "show"):
        _zone_show(args)
    elif action == "set":
        _zone_set(args)
    elif action == "clear":
        _zone_clear(args)
    else:
        print(colorize("Usage: structorium zone {show|set|clear}", "red"), file=sys.stderr)
        sys.exit(1)


def _zone_show(args):
    """Show zone classifications for all scanned files."""
    state_file = state_path(args)
    if not state_file.exists():
        print(colorize("No state file found — run a scan first.", "red"), file=sys.stderr)
        sys.exit(1)
    lang = resolve_lang(args)
    if not lang or not lang.file_finder:
        print(colorize("No language detected — run a scan first.", "red"), file=sys.stderr)
        sys.exit(1)

    path = Path(args.path)
    overrides = command_runtime(args).config.get("zone_overrides", {})

    files = lang.file_finder(path)
    zone_map = FileZoneMap(
        files, lang.zone_rules, rel_fn=rel, overrides=overrides or None
    )

    # Group files by zone
    by_zone: dict[str, list[str]] = {}
    for f in sorted(files, key=lambda f: rel(f)):
        zone = zone_map.get(f)
        by_zone.setdefault(zone.value, []).append(f)

    total = len(files)
    print(colorize(f"\nZone classifications ({total} files)\n", "bold"))

    for zone_val in ["production", "test", "config", "generated", "script", "vendor"]:
        zone_files = by_zone.get(zone_val, [])
        if not zone_files:
            continue
        print(colorize(f"  {zone_val} ({len(zone_files)} files)", "bold"))
        for f in zone_files:
            rp = rel(f)
            is_override = rp in overrides
            suffix = colorize(" (override)", "cyan") if is_override else ""
            print(f"    {rp}{suffix}")
        print()

    if overrides:
        print(colorize(f"  {len(overrides)} override(s) active", "dim"))
    print(colorize("  Override: structorium zone set <file> <zone>", "dim"))
    print(colorize("  Clear:    structorium zone clear <file>", "dim"))
    print_agent_plan(
        ["Fix misclassified files, then re-scan."],
        next_command="structorium scan",
    )


def _zone_set(args):
    """Set a zone override for a file."""
    filepath = args.zone_path
    zone_value = args.zone_value

    # Validate zone value
    valid_zones = {z.value for z in Zone}
    if zone_value not in valid_zones:
        print(
            colorize(
                f"Invalid zone: {zone_value}. Valid: {', '.join(sorted(valid_zones))}",
                "red",
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    normalized = rel(filepath)
    config = command_runtime(args).config
    config.setdefault("zone_overrides", {})[normalized] = zone_value
    try:
        config_mod.save_config(config)
    except OSError as e:
        print_error(f"could not save config: {e}")
        sys.exit(1)
    print(f"  Set {normalized} → {zone_value}")
    print(colorize("  Run `structorium scan` to apply.", "dim"))
    print(colorize("  Next command: `structorium scan`", "dim"))


def _zone_clear(args):
    """Clear a zone override for a file."""
    filepath = args.zone_path

    normalized = rel(filepath)
    config = command_runtime(args).config
    overrides = config.get("zone_overrides", {})
    if normalized in overrides:
        del overrides[normalized]
        try:
            config_mod.save_config(config)
        except OSError as e:
            print_error(f"could not save config: {e}")
            sys.exit(1)
        print(f"  Cleared override for {normalized}")
        print(colorize("  Run `structorium scan` to apply.", "dim"))
        print(colorize("  Next command: `structorium scan`", "dim"))
    else:
        print(colorize(f"  No override found for {normalized}", "yellow"))
