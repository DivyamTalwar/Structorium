"""CLI surface tests for dependency-impact exploration."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from app.commands.helpers.runtime import CommandRuntime
from app.commands.impact_cmd import cmd_impact
from cli import create_parser


def test_parser_accepts_bounded_impact_options() -> None:
    args = create_parser().parse_args(
        [
            "impact",
            "src/domain.py",
            "--direction",
            "dependents",
            "--depth",
            "4",
            "--max-nodes",
            "25",
            "--format",
            "json",
        ]
    )
    assert args.command == "impact"
    assert args.targets == ["src/domain.py"]
    assert args.depth == 4
    assert args.max_nodes == 25


def test_command_writes_json_with_mock_language(tmp_path: Path, monkeypatch) -> None:
    class FakeRun:
        @staticmethod
        def build_dep_graph(_path):
            return {
                "src/api.py": {"imports": {"src/domain.py"}},
                "src/domain.py": {"imports": set()},
            }

    class FakeLang:
        name = "fake"
        build_dep_graph = True

        @staticmethod
        def normalize_settings(settings):
            return settings

    monkeypatch.setattr("app.commands.impact_cmd.resolve_lang", lambda _args: FakeLang())
    monkeypatch.setattr(
        "app.commands.impact_cmd.lang_runtime.make_lang_run",
        lambda *_args, **_kwargs: FakeRun(),
    )
    output = tmp_path / "impact.json"
    args = Namespace(
        targets=["src/domain.py"],
        direction="dependents",
        depth=3,
        max_nodes=20,
        format="json",
        output=str(output),
        path=str(tmp_path),
        runtime=CommandRuntime(config={}, state={}, state_path=None),
    )
    cmd_impact(args)
    assert '"path": "src/api.py"' in output.read_text(encoding="utf-8")
