"""Dependency-impact algorithm and evidence renderer tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.impact import (
    analyze_impact,
    render_impact_json,
    render_impact_mermaid,
)


def _graph() -> dict:
    return {
        "src/api.py": {"imports": {"src/service.py"}},
        "src/worker.py": {"imports": {"src/service.py"}},
        "src/service.py": {"imports": {"src/domain.py"}},
        "src/domain.py": {"imports": set()},
        "tests/test_domain.py": {"imports": {"src/domain.py"}},
    }


def test_dependents_include_shortest_path_witnesses(tmp_path: Path) -> None:
    report = analyze_impact(
        _graph(), ["src/domain.py"], project_root=tmp_path, direction="dependents"
    )
    by_path = {entry["path"]: entry for entry in report["entries"]}
    assert by_path["src/service.py"]["witness"] == ["src/domain.py", "src/service.py"]
    assert by_path["src/api.py"]["witness"] == [
        "src/domain.py",
        "src/service.py",
        "src/api.py",
    ]


def test_directory_target_expands_to_matching_graph_nodes(tmp_path: Path) -> None:
    report = analyze_impact(
        _graph(), ["src"], project_root=tmp_path, direction="dependencies", max_depth=1
    )
    assert report["seeds"] == [
        "src/api.py",
        "src/domain.py",
        "src/service.py",
        "src/worker.py",
    ]


def test_budget_is_hard_bounded_and_marked_truncated(tmp_path: Path) -> None:
    report = analyze_impact(
        _graph(),
        ["src/domain.py"],
        project_root=tmp_path,
        direction="dependents",
        max_nodes=2,
    )
    assert len(report["entries"]) == 1
    assert report["node_count"] == 2
    assert report["truncated"] is True


def test_unknown_target_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no dependency graph nodes matched"):
        analyze_impact(_graph(), ["missing"], project_root=tmp_path)


def test_json_and_mermaid_are_deterministic(tmp_path: Path) -> None:
    report = analyze_impact(_graph(), ["src/domain.py"], project_root=tmp_path)
    assert json.loads(render_impact_json(report))["seeds"] == ["src/domain.py"]
    mermaid = render_impact_mermaid(report)
    assert mermaid.startswith("flowchart LR\n")
    assert "src/domain.py" in mermaid
    assert "classDef seed" in mermaid
