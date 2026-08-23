"""Version-controlled finding baselines and fail-closed regression comparison."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TypedDict

from core.discovery_api import safe_write_text

BASELINE_SCHEMA_VERSION = 1


class BaselineDiff(TypedDict):
    """Deterministic comparison between active findings and a captured baseline."""

    new: list[dict[str, Any]]
    resolved: list[dict[str, Any]]
    unchanged: list[dict[str, Any]]


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _fingerprint(finding: Mapping[str, Any]) -> str:
    identity = "\0".join(
        (
            str(finding.get("detector") or "unknown"),
            str(finding.get("file") or ".").replace("\\", "/"),
            str(finding.get("id") or ""),
        )
    )
    return hashlib.sha256(identity.encode("utf-8", errors="replace")).hexdigest()


def _active_entries(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    findings = state.get("findings")
    if not isinstance(findings, Mapping):
        return []
    entries: list[dict[str, Any]] = []
    for value in findings.values():
        if not isinstance(value, Mapping):
            continue
        if value.get("status") != "open" or value.get("suppressed"):
            continue
        entries.append(
            {
                "fingerprint": _fingerprint(value),
                "id": str(value.get("id") or ""),
                "detector": str(value.get("detector") or "unknown"),
                "file": str(value.get("file") or ".").replace("\\", "/"),
                "tier": int(value.get("tier") or 4),
                "confidence": str(value.get("confidence") or "unknown"),
            }
        )
    return sorted(entries, key=lambda item: item["fingerprint"])


def _checksum(entries: list[dict[str, Any]]) -> str:
    return hashlib.sha256(_canonical_json(entries).encode("utf-8")).hexdigest()


def build_baseline(state: Mapping[str, Any]) -> dict[str, Any]:
    """Capture active, unsuppressed findings in a deterministic baseline document."""
    entries = _active_entries(state)
    return {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "source": {
            "last_scan": state.get("last_scan"),
            "scan_count": int(state.get("scan_count") or 0),
        },
        "finding_count": len(entries),
        "findings": entries,
        "checksum": f"sha256:{_checksum(entries)}",
    }


def validate_baseline(document: Mapping[str, Any]) -> None:
    """Reject malformed or silently edited baseline documents."""
    if document.get("schema_version") != BASELINE_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported baseline schema: {document.get('schema_version')!r}"
        )
    findings = document.get("findings")
    if not isinstance(findings, list) or any(not isinstance(item, dict) for item in findings):
        raise ValueError("baseline findings must be a list of objects")
    fingerprints = [str(item.get("fingerprint") or "") for item in findings]
    if not all(fingerprints) or len(fingerprints) != len(set(fingerprints)):
        raise ValueError("baseline fingerprints must be non-empty and unique")
    if fingerprints != sorted(fingerprints):
        raise ValueError("baseline findings must be sorted by fingerprint")
    expected = f"sha256:{_checksum(findings)}"
    if document.get("checksum") != expected:
        raise ValueError("baseline checksum mismatch; recapture it explicitly")
    if document.get("finding_count") != len(findings):
        raise ValueError("baseline finding_count does not match findings")


def compare_baseline(
    state: Mapping[str, Any], document: Mapping[str, Any]
) -> BaselineDiff:
    """Return new, resolved, and unchanged findings relative to a valid baseline."""
    validate_baseline(document)
    current = {entry["fingerprint"]: entry for entry in _active_entries(state)}
    captured = {
        str(entry["fingerprint"]): entry
        for entry in document["findings"]
        if isinstance(entry, dict)
    }
    return {
        "new": [current[key] for key in sorted(current.keys() - captured.keys())],
        "resolved": [captured[key] for key in sorted(captured.keys() - current.keys())],
        "unchanged": [current[key] for key in sorted(current.keys() & captured.keys())],
    }


def load_baseline(path: Path) -> dict[str, Any]:
    """Load and validate a baseline JSON document."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"baseline not found: {path}") from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read baseline {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError("baseline root must be a JSON object")
    validate_baseline(document)
    return document


def write_baseline(
    document: Mapping[str, Any], path: Path, *, overwrite: bool = False
) -> Path:
    """Write a validated baseline atomically, refusing implicit replacement."""
    validate_baseline(document)
    if path.exists() and not overwrite:
        raise ValueError(f"baseline already exists: {path}; pass --force to replace it")
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_write_text(path, json.dumps(document, indent=2, sort_keys=True) + "\n")
    return path.resolve()


__all__ = [
    "BASELINE_SCHEMA_VERSION",
    "BaselineDiff",
    "build_baseline",
    "compare_baseline",
    "load_baseline",
    "validate_baseline",
    "write_baseline",
]
