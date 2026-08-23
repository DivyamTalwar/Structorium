"""CLI tests for finding baseline capture and enforcement."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from app.commands.baseline_cmd import cmd_baseline
from app.commands.helpers.runtime import CommandRuntime
from cli import create_parser


def test_parser_exposes_capture_and_check() -> None:
    capture = create_parser().parse_args(["baseline", "capture", "--force"])
    check = create_parser().parse_args(["baseline", "check", "--max-new", "2", "--json"])
    assert capture.baseline_action == "capture"
    assert capture.force is True
    assert check.baseline_action == "check"
    assert check.max_new == 2
    assert check.json is True


def test_check_uses_distinct_exit_code_for_regression(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline.json"
    clean_state = {
        "last_scan": "2026-08-24T00:00:00+00:00",
        "scan_count": 1,
        "findings": {},
    }
    capture_args = Namespace(
        baseline_action="capture",
        output=str(baseline_path),
        force=False,
        runtime=CommandRuntime(config={}, state=clean_state, state_path=None),
    )
    cmd_baseline(capture_args)

    finding = {
        "id": "coupling::src/new.py",
        "detector": "coupling",
        "file": "src/new.py",
        "tier": 2,
        "confidence": "high",
        "status": "open",
    }
    check_args = Namespace(
        baseline_action="check",
        baseline=str(baseline_path),
        max_new=0,
        json=False,
        runtime=CommandRuntime(
            config={}, state={**clean_state, "findings": {finding["id"]: finding}}, state_path=None
        ),
    )
    with pytest.raises(SystemExit) as exc:
        cmd_baseline(check_args)
    assert exc.value.code == 3
