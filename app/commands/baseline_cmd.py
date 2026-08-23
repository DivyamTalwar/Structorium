"""Capture and enforce version-controlled Structorium finding baselines."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.commands.helpers.runtime import command_runtime
from core.output_api import colorize
from engine._state.baseline import (
    build_baseline,
    compare_baseline,
    load_baseline,
    write_baseline,
)


def _require_scan(state: dict) -> None:
    if not state.get("last_scan"):
        print(colorize("No completed scan found. Run `structorium scan` first.", "red"), file=sys.stderr)
        raise SystemExit(2)


def _capture(args: argparse.Namespace, state: dict) -> None:
    document = build_baseline(state)
    output = write_baseline(
        document,
        Path(args.output),
        overwrite=bool(getattr(args, "force", False)),
    )
    print(colorize(f"Captured {document['finding_count']} findings in {output}", "green"))


def _check(args: argparse.Namespace, state: dict) -> None:
    document = load_baseline(Path(args.baseline))
    diff = compare_baseline(state, document)
    payload = {
        "baseline": str(Path(args.baseline)),
        "new_count": len(diff["new"]),
        "resolved_count": len(diff["resolved"]),
        "unchanged_count": len(diff["unchanged"]),
        **diff,
    }
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(colorize("\nStructorium baseline ratchet", "bold"))
        print(f"  New: {payload['new_count']}")
        print(f"  Resolved since capture: {payload['resolved_count']}")
        print(f"  Unchanged: {payload['unchanged_count']}")
        for finding in diff["new"]:
            print(colorize(f"  + T{finding['tier']} {finding['id']}", "red"))

    max_new = int(getattr(args, "max_new", 0))
    if payload["new_count"] > max_new:
        print(
            colorize(
                f"Baseline failed: {payload['new_count']} new findings exceeds --max-new {max_new}",
                "red",
            ),
            file=sys.stderr,
        )
        raise SystemExit(3)
    print(colorize("Baseline passed", "green"), file=sys.stderr)


def cmd_baseline(args: argparse.Namespace) -> None:
    """Dispatch baseline capture/check operations."""
    state = command_runtime(args).state
    _require_scan(state)
    action = getattr(args, "baseline_action", None)
    if action == "capture":
        _capture(args, state)
        return
    if action == "check":
        _check(args, state)
        return
    raise ValueError("baseline action must be capture or check")


__all__ = ["cmd_baseline"]
