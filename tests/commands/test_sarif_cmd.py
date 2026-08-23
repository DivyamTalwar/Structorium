"""CLI surface tests for SARIF export."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from app.commands.helpers.runtime import CommandRuntime
from app.commands.sarif_cmd import cmd_sarif
from cli import create_parser


def test_parser_accepts_sarif_options() -> None:
    args = create_parser().parse_args(
        ["sarif", "--output", "out.sarif", "--include-suppressed", "--max-results", "99"]
    )
    assert args.command == "sarif"
    assert args.output == "out.sarif"
    assert args.include_suppressed is True
    assert args.max_results == 99


def test_command_requires_completed_scan(tmp_path: Path) -> None:
    args = Namespace(
        output=str(tmp_path / "out.sarif"),
        path=str(tmp_path),
        include_resolved=False,
        include_suppressed=False,
        max_results=5_000,
        runtime=CommandRuntime(config={}, state={"last_scan": None}, state_path=None),
    )
    with pytest.raises(SystemExit) as exc:
        cmd_sarif(args)
    assert exc.value.code == 2
