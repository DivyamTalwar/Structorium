"""Tests for incremental AI review memory helpers."""

from __future__ import annotations

import subprocess

from intelligence.ai.incremental_memory import (
    build_incremental_review_memory,
    record_review_import_memory,
    review_memory_path,
)


def _git(repo, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(tmp_path) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "bot@example.com")
    _git(tmp_path, "config", "user.name", "Structorium Bot")
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "a.py").write_text("def run():\n    return 1\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "initial")


def test_record_and_build_incremental_review_memory(tmp_path):
    _init_repo(tmp_path)
    payload = {
        "findings": [
            {
                "dimension": "design_coherence",
                "related_files": ["src/a.py", "src/b.py"],
            }
        ]
    }
    record_review_import_memory(
        repo_root=tmp_path,
        findings_payload=payload,
        assessment_mode="trusted_internal",
    )

    memory = build_incremental_review_memory(
        repo_root=tmp_path,
        focus_files=["src/a.py"],
        max_feedback_entries=5,
        max_commits=20,
    )

    assert memory["status"] == "ready"
    feedback_entries = memory.get("feedback_entries", [])
    assert isinstance(feedback_entries, list)
    assert feedback_entries
    assert feedback_entries[0]["assessment_mode"] == "trusted_internal"


def test_incremental_review_memory_tolerates_corrupt_file(tmp_path):
    _init_repo(tmp_path)
    path = review_memory_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not-json")

    memory = build_incremental_review_memory(
        repo_root=tmp_path,
        focus_files=[],
        max_feedback_entries=3,
        max_commits=5,
    )
    assert memory["status"] in {"ready", "unavailable"}
    assert path.exists()
