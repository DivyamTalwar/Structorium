"""Finding baseline integrity and ratchet tests."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from engine._state.baseline import (
    build_baseline,
    compare_baseline,
    load_baseline,
    write_baseline,
)


def _finding(fid: str, *, status: str = "open", suppressed: bool = False) -> dict:
    return {
        "id": fid,
        "detector": "coupling",
        "file": fid.rsplit("::", 1)[-1],
        "tier": 2,
        "confidence": "high",
        "status": status,
        "suppressed": suppressed,
    }


def _state(*findings: dict) -> dict:
    return {
        "last_scan": "2026-08-24T00:00:00+00:00",
        "scan_count": 4,
        "findings": {item["id"]: item for item in findings},
    }


def test_baseline_only_captures_active_unsuppressed_findings() -> None:
    document = build_baseline(
        _state(
            _finding("coupling::src/a.py"),
            _finding("coupling::src/b.py", status="fixed"),
            _finding("coupling::src/c.py", suppressed=True),
        )
    )
    assert document["finding_count"] == 1
    assert document["findings"][0]["id"] == "coupling::src/a.py"


def test_compare_reports_new_resolved_and_unchanged() -> None:
    baseline = build_baseline(
        _state(_finding("coupling::src/a.py"), _finding("coupling::src/b.py"))
    )
    diff = compare_baseline(
        _state(_finding("coupling::src/b.py"), _finding("coupling::src/c.py")),
        baseline,
    )
    assert [item["id"] for item in diff["new"]] == ["coupling::src/c.py"]
    assert [item["id"] for item in diff["resolved"]] == ["coupling::src/a.py"]
    assert [item["id"] for item in diff["unchanged"]] == ["coupling::src/b.py"]


def test_checksum_rejects_silent_baseline_edit() -> None:
    document = build_baseline(_state(_finding("coupling::src/a.py")))
    edited = copy.deepcopy(document)
    edited["findings"][0]["tier"] = 4
    with pytest.raises(ValueError, match="checksum mismatch"):
        compare_baseline(_state(), edited)


def test_write_refuses_implicit_overwrite_and_round_trips(tmp_path: Path) -> None:
    path = tmp_path / ".structorium" / "baseline.json"
    document = build_baseline(_state(_finding("coupling::src/a.py")))
    write_baseline(document, path)
    assert load_baseline(path) == document
    with pytest.raises(ValueError, match="already exists"):
        write_baseline(document, path)


def test_fingerprint_is_independent_of_tier_and_confidence() -> None:
    first = build_baseline(_state(_finding("coupling::src/a.py")))
    changed = _finding("coupling::src/a.py")
    changed["tier"] = 4
    changed["confidence"] = "low"
    second = build_baseline(_state(changed))
    assert first["findings"][0]["fingerprint"] == second["findings"][0]["fingerprint"]
