"""Persistent content-addressed cache for deterministic objective scans."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core._internal.text_utils import get_project_root
from languages._framework.base.types import DetectorPhase
from languages._framework.runtime import LangRun
from versioning import compute_tool_hash

CACHE_SCHEMA = 1


@dataclass(frozen=True)
class ScanCacheLookup:
    """Prepared cache key plus an optional normalized result."""

    cache_path: Path
    key: str
    files: dict[str, dict[str, int | str]]
    findings: list[dict[str, Any]] | None = None
    potentials: dict[str, int] | None = None

    @property
    def hit(self) -> bool:
        return self.findings is not None and self.potentials is not None


def _read_document(cache_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _source_files(scan_path: Path, lang: LangRun) -> list[Path]:
    if lang.file_finder is None:
        return []
    root = get_project_root().resolve()
    candidates = lang.file_finder(root)
    resolved: set[Path] = set()
    scan_root = scan_path.resolve()
    for candidate in candidates:
        path = Path(candidate)
        if not path.is_absolute():
            path = root / path
        path = path.resolve()
        if path.is_file() and (path.is_relative_to(scan_root) or scan_root == root):
            resolved.add(path)
    policy = root / "structorium.toml"
    if policy.is_file():
        resolved.add(policy)
    return sorted(resolved)


def _build_manifest(
    paths: list[Path], previous: dict[str, Any]
) -> dict[str, dict[str, int | str]]:
    root = get_project_root().resolve()
    manifest: dict[str, dict[str, int | str]] = {}
    previous_files = previous.get("files", {})
    if not isinstance(previous_files, dict):
        previous_files = {}

    for path in paths:
        try:
            stat = path.stat()
        except OSError:
            continue
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            relative = path.as_posix()
        old = previous_files.get(relative, {})
        unchanged = (
            isinstance(old, dict)
            and old.get("size") == stat.st_size
            and old.get("mtime_ns") == stat.st_mtime_ns
            and isinstance(old.get("sha256"), str)
        )
        if unchanged:
            digest = str(old["sha256"])
        else:
            try:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                continue
        manifest[relative] = {
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "sha256": digest,
        }
    return manifest


def prepare_scan_cache(
    scan_path: Path,
    lang: LangRun,
    phases: list[DetectorPhase],
    *,
    profile: str,
    include_slow: bool,
    zone_overrides: dict[str, str] | None,
) -> ScanCacheLookup:
    """Return a cache lookup, hashing only files whose stat fingerprint changed."""
    root = get_project_root().resolve()
    cache_path = root / ".structorium" / "cache" / "objective-scan-v1.json"
    previous = _read_document(cache_path)
    manifest = _build_manifest(_source_files(scan_path, lang), previous)
    key_payload = {
        "schema": CACHE_SCHEMA,
        "tool": compute_tool_hash(),
        "language": lang.name,
        "profile": profile,
        "include_slow": include_slow,
        "phases": [(phase.label, phase.slow) for phase in phases],
        "settings": lang.runtime_settings,
        "options": lang.runtime_options,
        "zone_overrides": zone_overrides or {},
        "files": manifest,
    }
    key = hashlib.sha256(
        json.dumps(key_payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    result = previous.get("result", {})
    if previous.get("key") == key and isinstance(result, dict):
        findings = result.get("findings")
        potentials = result.get("potentials")
        if isinstance(findings, list) and isinstance(potentials, dict):
            return ScanCacheLookup(
                cache_path, key, manifest, findings, potentials
            )
    return ScanCacheLookup(cache_path, key, manifest)


def store_scan_cache(
    lookup: ScanCacheLookup,
    findings: list[dict[str, Any]],
    potentials: dict[str, int],
) -> None:
    """Atomically persist a successful objective-scan result."""
    document = {
        "schema": CACHE_SCHEMA,
        "key": lookup.key,
        "files": lookup.files,
        "result": {"findings": findings, "potentials": potentials},
    }
    lookup.cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = lookup.cache_path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(document, sort_keys=True, separators=(",", ":"), default=str),
        encoding="utf-8",
    )
    temporary.replace(lookup.cache_path)


__all__ = ["ScanCacheLookup", "prepare_scan_cache", "store_scan_cache"]
