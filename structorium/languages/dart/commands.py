"""Dart detect-subcommand wrappers + command registry."""

from __future__ import annotations

import argparse

from structorium.languages._framework.commands_base import (
    build_standard_detect_registry,
    make_cmd_complexity,
    make_cmd_cycles,
    make_cmd_deps,
    make_cmd_dupes,
    make_cmd_large,
    make_cmd_orphaned,
)
from structorium.languages.dart.detectors.deps import build_dep_graph
from structorium.languages.dart.extractors import extract_functions, find_dart_files
from structorium.languages.dart.phases import DART_COMPLEXITY_SIGNALS

_cmd_large_impl = make_cmd_large(find_dart_files, default_threshold=500)
_cmd_complexity_impl = make_cmd_complexity(
    find_dart_files, DART_COMPLEXITY_SIGNALS, default_threshold=16
)
_cmd_deps_impl = make_cmd_deps(
    build_dep_graph_fn=build_dep_graph,
    empty_message="No Dart dependencies detected.",
    import_count_label="Imports",
    top_imports_label="Top imports",
)
_cmd_cycles_impl = make_cmd_cycles(build_dep_graph_fn=build_dep_graph)
_cmd_orphaned_impl = make_cmd_orphaned(
    build_dep_graph_fn=build_dep_graph,
    extensions=[".dart"],
    extra_entry_patterns=[
        "/main.dart",
        "/bin/",
        "/tool/",
        "/web/",
        "/test/",
        "/integration_test/",
    ],
    extra_barrel_names={"index.dart"},
)
_cmd_dupes_impl = make_cmd_dupes(extract_functions_fn=extract_functions)


def cmd_large(args: argparse.Namespace) -> None:
    _cmd_large_impl(args)


def cmd_complexity(args: argparse.Namespace) -> None:
    _cmd_complexity_impl(args)


def cmd_deps(args: argparse.Namespace) -> None:
    _cmd_deps_impl(args)


def cmd_cycles(args: argparse.Namespace) -> None:
    _cmd_cycles_impl(args)


def cmd_orphaned(args: argparse.Namespace) -> None:
    _cmd_orphaned_impl(args)


def cmd_dupes(args: argparse.Namespace) -> None:
    _cmd_dupes_impl(args)


def get_detect_commands() -> dict[str, object]:
    """Return the standard detect command registry for Dart."""
    return build_standard_detect_registry(
        cmd_deps=cmd_deps,
        cmd_cycles=cmd_cycles,
        cmd_orphaned=cmd_orphaned,
        cmd_dupes=cmd_dupes,
        cmd_large=cmd_large,
        cmd_complexity=cmd_complexity,
    )
