"""Tests for temporal coupling ripple radar."""

from __future__ import annotations

import subprocess

from intelligence.ai.temporal_coupling import compute_temporal_coupling


def _git(repo, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _commit(repo, message: str) -> None:
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", message)


def test_temporal_coupling_detects_hotspot_pair(tmp_path):
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "bot@example.com")
    _git(tmp_path, "config", "user.name", "Structorium Bot")

    (tmp_path / "a.py").write_text("A = 1\n")
    (tmp_path / "b.py").write_text("B = 1\n")
    _commit(tmp_path, "seed")

    (tmp_path / "a.py").write_text("A = 2\n")
    (tmp_path / "b.py").write_text("B = 2\n")
    _commit(tmp_path, "change a+b once")

    (tmp_path / "a.py").write_text("A = 3\n")
    (tmp_path / "b.py").write_text("B = 3\n")
    _commit(tmp_path, "change a+b twice")

    (tmp_path / "c.py").write_text("C = 1\n")
    (tmp_path / "a.py").write_text("A = 4\n")
    _commit(tmp_path, "change a+c")

    radar = compute_temporal_coupling(
        repo_root=tmp_path,
        focus_files=["a.py"],
        max_commits=20,
    )

    assert radar["status"] == "ready"
    hotspots = radar.get("hotspots", [])
    assert isinstance(hotspots, list)
    assert hotspots
    assert any(
        {row.get("left"), row.get("right")} == {"a.py", "b.py"}
        and int(row.get("co_change_commits", 0)) >= 2
        for row in hotspots
        if isinstance(row, dict)
    )
