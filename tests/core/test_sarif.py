"""Contract tests for deterministic, GitHub-compatible SARIF export."""

from __future__ import annotations

import json
from pathlib import Path

from core.sarif import SARIF_VERSION, build_sarif, write_sarif


def _finding(fid: str, *, tier: int = 2, line: int = 8, status: str = "open") -> dict:
    return {
        "id": fid,
        "detector": "cycles",
        "file": "src/domain.py",
        "tier": tier,
        "confidence": "high",
        "summary": "Dependency cycle",
        "detail": {"line": line},
        "status": status,
    }


def test_build_sarif_has_stable_fingerprint_across_line_moves(tmp_path: Path) -> None:
    first = build_sarif({"findings": {"one": _finding("cycles::src/domain.py::a", line=8)}}, project_root=tmp_path)
    second = build_sarif({"findings": {"one": _finding("cycles::src/domain.py::a", line=80)}}, project_root=tmp_path)

    first_result = first["runs"][0]["results"][0]
    second_result = second["runs"][0]["results"][0]
    assert first["version"] == SARIF_VERSION
    assert first_result["partialFingerprints"] == second_result["partialFingerprints"]
    assert first_result["locations"][0]["physicalLocation"]["region"] == {"startLine": 8}


def test_build_sarif_filters_and_bounds_results(tmp_path: Path) -> None:
    state = {
        "findings": {
            "low": _finding("cycles::src/domain.py::low", tier=4),
            "high": _finding("cycles::src/domain.py::high", tier=1),
            "fixed": _finding("cycles::src/domain.py::fixed", status="fixed"),
            "hidden": {**_finding("cycles::src/domain.py::hidden"), "suppressed": True},
        }
    }
    document = build_sarif(state, project_root=tmp_path, max_results=1)
    results = document["runs"][0]["results"]

    assert len(results) == 1
    assert results[0]["properties"]["structoriumFindingId"].endswith("::high")
    assert results[0]["level"] == "error"


def test_write_sarif_emits_round_trippable_json(tmp_path: Path) -> None:
    output = tmp_path / "artifacts" / "structorium.sarif"
    document = build_sarif({"findings": {}}, project_root=tmp_path)
    resolved = write_sarif(document, output)

    assert resolved == output.resolve()
    assert json.loads(output.read_text(encoding="utf-8")) == document
