"""Deterministic SARIF 2.1.0 export for persisted Structorium findings."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from core.discovery_api import safe_write_text

SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
SARIF_VERSION = "2.1.0"

_CONFIDENCE_ORDER = {"high": 0, "medium": 1, "low": 2}


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _finding_line(detail: object) -> int:
    """Resolve a best-effort source line while remaining tolerant of detector shapes."""
    if not isinstance(detail, Mapping):
        return 1
    for key in ("line", "line_number", "start_line", "lineno"):
        parsed = _positive_int(detail.get(key))
        if parsed is not None:
            return parsed
    lines = detail.get("lines")
    if isinstance(lines, (list, tuple)):
        parsed_lines = [line for item in lines if (line := _positive_int(item))]
        if parsed_lines:
            return min(parsed_lines)
    return 1


def _artifact_uri(file_value: object, project_root: Path) -> str:
    """Return a repository-relative, POSIX SARIF artifact URI when possible."""
    raw = str(file_value or ".").replace("\\", "/")
    if raw.startswith("file://"):
        raw = raw[7:]
    candidate = Path(raw)
    if candidate.is_absolute():
        try:
            raw = str(candidate.resolve().relative_to(project_root.resolve()))
        except (OSError, ValueError):
            raw = candidate.name
    normalized = PurePosixPath(raw).as_posix().lstrip("./")
    return normalized or "."


def _fingerprint(finding: Mapping[str, Any], artifact_uri: str) -> str:
    stable_id = str(finding.get("id") or "")
    detector = str(finding.get("detector") or "unknown")
    identity = f"{detector}\0{artifact_uri}\0{stable_id}"
    return hashlib.sha256(identity.encode("utf-8", errors="replace")).hexdigest()


def _level(tier: object) -> str:
    parsed = _positive_int(tier) or 4
    if parsed <= 1:
        return "error"
    if parsed == 2:
        return "warning"
    return "note"


def _active_findings(
    state: Mapping[str, Any],
    *,
    include_resolved: bool,
    include_suppressed: bool,
) -> list[Mapping[str, Any]]:
    findings = state.get("findings")
    if not isinstance(findings, Mapping):
        return []
    selected: list[Mapping[str, Any]] = []
    for value in findings.values():
        if not isinstance(value, Mapping):
            continue
        if not include_resolved and value.get("status") != "open":
            continue
        if not include_suppressed and bool(value.get("suppressed")):
            continue
        selected.append(value)
    return sorted(
        selected,
        key=lambda item: (
            _positive_int(item.get("tier")) or 99,
            _CONFIDENCE_ORDER.get(str(item.get("confidence", "")).lower(), 3),
            str(item.get("id") or ""),
        ),
    )


def build_sarif(
    state: Mapping[str, Any],
    *,
    project_root: Path | None = None,
    include_resolved: bool = False,
    include_suppressed: bool = False,
    max_results: int = 5_000,
) -> dict[str, Any]:
    """Build a GitHub-compatible SARIF document from Structorium state.

    The export is deliberately bounded and deterministic. Stable fingerprints use
    Structorium finding identities rather than source line numbers, so line-only
    movement does not create duplicate alerts.
    """
    project_root = project_root or Path.cwd()
    if max_results < 1:
        raise ValueError("max_results must be at least 1")
    findings = _active_findings(
        state,
        include_resolved=include_resolved,
        include_suppressed=include_suppressed,
    )[:max_results]

    detector_names = sorted(
        {str(finding.get("detector") or "unknown") for finding in findings}
    )
    rules = [
        {
            "id": detector,
            "name": detector.replace("_", " ").title(),
            "shortDescription": {"text": f"Structorium {detector} finding"},
            "helpUri": "https://github.com/DivyamTalwar/Structorium#-detector-registry--complete-reference",
            "properties": {"tags": ["maintainability", "architecture"]},
        }
        for detector in detector_names
    ]

    results: list[dict[str, Any]] = []
    for finding in findings:
        detector = str(finding.get("detector") or "unknown")
        artifact_uri = _artifact_uri(finding.get("file"), project_root)
        result: dict[str, Any] = {
            "ruleId": detector,
            "level": _level(finding.get("tier")),
            "message": {"text": str(finding.get("summary") or finding.get("id") or detector)},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": artifact_uri, "uriBaseId": "%SRCROOT%"},
                        "region": {"startLine": _finding_line(finding.get("detail"))},
                    }
                }
            ],
            "partialFingerprints": {
                "structoriumFinding/v1": _fingerprint(finding, artifact_uri)
            },
            "properties": {
                "structoriumFindingId": str(finding.get("id") or ""),
                "tier": _positive_int(finding.get("tier")) or 4,
                "confidence": str(finding.get("confidence") or "unknown"),
                "status": str(finding.get("status") or "unknown"),
            },
        }
        if finding.get("suppressed"):
            result["suppressions"] = [
                {
                    "kind": "external",
                    "justification": str(
                        finding.get("suppression_pattern") or "Suppressed in Structorium state"
                    ),
                }
            ]
        results.append(result)

    return {
        "$schema": SARIF_SCHEMA,
        "version": SARIF_VERSION,
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Structorium",
                        "informationUri": "https://github.com/DivyamTalwar/Structorium",
                        "rules": rules,
                    }
                },
                "automationDetails": {"id": "structorium/default"},
                "originalUriBaseIds": {
                    "%SRCROOT%": {"uri": project_root.resolve().as_uri() + "/"}
                },
                "results": results,
            }
        ],
    }


def write_sarif(document: Mapping[str, Any], output: Path) -> Path:
    """Write a SARIF document atomically and return its resolved output path."""
    output = output.expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    safe_write_text(output, json.dumps(document, indent=2, sort_keys=True) + "\n")
    return output.resolve()


__all__ = ["SARIF_SCHEMA", "SARIF_VERSION", "build_sarif", "write_sarif"]
