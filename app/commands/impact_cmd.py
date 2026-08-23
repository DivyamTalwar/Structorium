"""CLI command for bounded dependency blast-radius exploration."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.commands.helpers.lang import resolve_lang, resolve_lang_settings
from app.commands.helpers.runtime import command_runtime
from core.discovery_api import safe_write_text
from core.output_api import colorize
from engine.impact import (
    analyze_impact,
    render_impact_json,
    render_impact_mermaid,
    render_impact_text,
)
from languages import runtime as lang_runtime


def cmd_impact(args: argparse.Namespace) -> None:
    """Build the language dependency graph and explain a bounded change radius."""
    lang = resolve_lang(args)
    if lang is None or not lang.build_dep_graph:
        print(
            colorize("No dependency-graph language integration is available.", "red"),
            file=sys.stderr,
        )
        raise SystemExit(2)

    project_root = Path(getattr(args, "path", None) or ".").resolve()
    runtime = command_runtime(args)
    lang_run = lang_runtime.make_lang_run(
        lang,
        overrides=lang_runtime.LangRunOverrides(
            runtime_settings=resolve_lang_settings(runtime.config, lang)
        ),
    )
    try:
        graph = lang_run.build_dep_graph(project_root)
    except (OSError, UnicodeDecodeError, ValueError, TypeError, RuntimeError) as exc:
        print(
            colorize(f"Could not build dependency graph: {exc}", "red"),
            file=sys.stderr,
        )
        raise SystemExit(2) from exc

    report = analyze_impact(
        graph,
        list(args.targets),
        project_root=project_root,
        direction=args.direction,
        max_depth=args.depth,
        max_nodes=args.max_nodes,
    )
    renderers = {
        "text": render_impact_text,
        "json": render_impact_json,
        "mermaid": render_impact_mermaid,
    }
    rendered = renderers[args.format](report)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        safe_write_text(output, rendered)
        print(colorize(f"Wrote dependency impact to {output.resolve()}", "green"))
    else:
        print(rendered, end="")


__all__ = ["cmd_impact"]
