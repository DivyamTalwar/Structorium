"""Visualization command handlers — thin wrappers delegating to output.visualize."""

from __future__ import annotations

import argparse

from structorium.app.output.visualize import cmd_tree as _cmd_tree
from structorium.app.output.visualize import cmd_viz as _cmd_viz


def cmd_viz(args: argparse.Namespace) -> None:
    """Generate HTML treemap visualization."""
    _cmd_viz(args)


def cmd_tree(args: argparse.Namespace) -> None:
    """Print annotated codebase tree to terminal."""
    _cmd_tree(args)


__all__ = ["cmd_tree", "cmd_viz"]
