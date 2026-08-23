"""CLI command for exporting persisted findings as SARIF 2.1.0."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.commands.helpers.runtime import command_runtime
from core.output_api import colorize
from core.sarif import build_sarif, write_sarif


def cmd_sarif(args: argparse.Namespace) -> None:
    """Export the current Structorium finding state for CI code-scanning tools."""
    runtime = command_runtime(args)
    if not runtime.state.get("last_scan"):
        print(colorize("No completed scan found. Run `structorium scan` first.", "red"), file=sys.stderr)
        raise SystemExit(2)

    project_root = Path(getattr(args, "path", None) or ".").resolve()
    document = build_sarif(
        runtime.state,
        project_root=project_root,
        include_resolved=bool(getattr(args, "include_resolved", False)),
        include_suppressed=bool(getattr(args, "include_suppressed", False)),
        max_results=int(getattr(args, "max_results", 5_000)),
    )
    output = write_sarif(document, Path(args.output))
    result_count = len(document["runs"][0]["results"])
    print(colorize(f"Wrote {result_count} findings to {output}", "green"))


__all__ = ["cmd_sarif"]
