"""Tests for new-code architecture gate logic."""

from __future__ import annotations

import subprocess

from intelligence.new_code_gate import (
    evaluate_new_code_gate,
    resolve_new_code_gate_settings,
)


def _git(repo, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _setup_repo_with_change(tmp_path):
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "bot@example.com")
    _git(tmp_path, "config", "user.name", "Structorium Bot")

    a_path = tmp_path / "a.py"
    b_path = tmp_path / "b.py"
    a_path.write_text("def a():\n    return 1\n")
    b_path.write_text("def b():\n    return 1\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "initial")

    a_path.write_text("def a():\n    return 2\n")
    _git(tmp_path, "add", "a.py")
    _git(tmp_path, "commit", "-m", "change a")


def test_new_code_gate_detects_only_changed_lines(tmp_path):
    _setup_repo_with_change(tmp_path)
    settings = resolve_new_code_gate_settings(
        {
            "new_code_gate_enabled": True,
            "new_code_gate_policy": "strict",
            "new_code_gate_base_ref": "HEAD~1",
        }
    )
    state = {
        "scan_path": ".",
        "findings": {
            "f1": {
                "id": "f1",
                "detector": "smells",
                "file": "a.py",
                "tier": 2,
                "summary": "debug artifact",
                "status": "open",
                "detail": {"line": 2},
            },
            "f2": {
                "id": "f2",
                "detector": "smells",
                "file": "a.py",
                "tier": 3,
                "summary": "old code finding",
                "status": "open",
                "detail": {"line": 200},
            },
            "f3": {
                "id": "f3",
                "detector": "smells",
                "file": "b.py",
                "tier": 1,
                "summary": "unchanged file",
                "status": "open",
                "detail": {"line": 1},
            },
        },
    }

    result = evaluate_new_code_gate(
        state=state,
        repo_root=tmp_path,
        settings=settings,
        scan_path=".",
    )

    assert result.enabled is True
    assert result.new_findings == 1
    assert result.new_high == 1
    assert result.new_critical == 0
    assert result.passed is False
    assert len(result.findings) == 1
    assert result.findings[0].finding_id == "f1"


def test_resolve_new_code_gate_policy_normalizes_profile_name():
    settings = resolve_new_code_gate_settings(
        {
            "new_code_gate_enabled": True,
            "new_code_gate_policy": "ai-generated-code",
        }
    )
    assert settings.enabled is True
    assert settings.policy.name == "ai_generated_code"
