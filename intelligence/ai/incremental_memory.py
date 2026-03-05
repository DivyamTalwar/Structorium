"""Incremental review memory for commit-aware AI review context."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.discovery_api import safe_write_text

_MEMORY_FILE_NAME = "ai_review_memory.json"
_COMMIT_HEADER_PREFIX = "__C__"


def review_memory_path(repo_root: Path) -> Path:
    """Return persisted memory path under .structorium."""
    return repo_root / ".structorium" / _MEMORY_FILE_NAME


def record_review_import_memory(
    *,
    repo_root: Path,
    findings_payload: dict[str, Any],
    assessment_mode: str,
    max_entries: int = 240,
) -> None:
    """Persist one durable memory entry for imported review output."""
    findings = findings_payload.get("findings", [])
    if not isinstance(findings, list):
        findings = []

    touched_files = _extract_touched_files(findings)
    touched_dimensions = _extract_dimensions(findings)
    entry = {
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "commit_sha": _git_head_sha(repo_root),
        "assessment_mode": assessment_mode,
        "finding_count": len(findings),
        "dimensions": touched_dimensions[:24],
        "files": touched_files[:40],
    }

    path = review_memory_path(repo_root)
    data = _load_memory_file(path)
    entries = data.get("entries", [])
    if not isinstance(entries, list):
        entries = []
    entries.append(entry)
    if len(entries) > max_entries:
        entries = entries[-max_entries:]
    data["entries"] = entries
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_write_text(path, json.dumps(data, indent=2) + "\n")


def build_incremental_review_memory(
    *,
    repo_root: Path,
    focus_files: list[str],
    max_feedback_entries: int,
    max_commits: int,
) -> dict[str, object]:
    """Build combined memory from persisted review feedback and git commit history."""
    focus = {_normalize_path(path) for path in focus_files if isinstance(path, str) and path}

    memory_data = _load_memory_file(review_memory_path(repo_root))
    stored_entries = memory_data.get("entries", [])
    if not isinstance(stored_entries, list):
        stored_entries = []

    feedback_entries: list[dict[str, object]] = []
    for item in reversed(stored_entries):
        if not isinstance(item, dict):
            continue
        files = item.get("files", [])
        if focus and isinstance(files, list):
            normalized_files = {
                _normalize_path(path)
                for path in files
                if isinstance(path, str) and path
            }
            if normalized_files and not normalized_files.intersection(focus):
                continue
        feedback_entries.append(
            {
                "recorded_at": str(item.get("recorded_at", "")),
                "commit_sha": str(item.get("commit_sha", "")),
                "assessment_mode": str(item.get("assessment_mode", "")),
                "finding_count": _safe_int(item.get("finding_count")),
                "dimensions": _string_list(item.get("dimensions"), limit=8),
                "files": _string_list(item.get("files"), limit=8),
            }
        )
        if len(feedback_entries) >= max_feedback_entries:
            break

    commits = _recent_commits(repo_root=repo_root, focus=focus, max_commits=max_commits)
    if commits is None:
        return {
            "status": "unavailable",
            "reason": "git_history_unavailable",
            "feedback_entries": feedback_entries,
        }
    return {
        "status": "ready",
        "focus_file_count": len(focus),
        "feedback_entries": feedback_entries,
        "recent_commits": commits,
    }


def _load_memory_file(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"entries": []}
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {"entries": []}
    if not isinstance(payload, dict):
        return {"entries": []}
    return payload


def _git_head_sha(repo_root: Path) -> str:
    output = _git_output(repo_root, ["rev-parse", "HEAD"])
    if output is None:
        return ""
    return output.strip()


def _recent_commits(
    *,
    repo_root: Path,
    focus: set[str],
    max_commits: int,
) -> list[dict[str, object]] | None:
    raw = _git_output(
        repo_root,
        [
            "log",
            "--date-order",
            f"-n{max(1, max_commits)}",
            f"--pretty=format:{_COMMIT_HEADER_PREFIX}%H|%ct|%s",
            "--name-only",
        ],
    )
    if raw is None:
        return None

    commits: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for line in raw.splitlines():
        text = line.strip()
        if not text:
            continue
        if text.startswith(_COMMIT_HEADER_PREFIX):
            if current is not None and _commit_matches_focus(current, focus):
                commits.append(_compact_commit(current))
            current = _parse_commit_header(text)
            continue
        if current is None:
            continue
        files = current.setdefault("files", [])
        if isinstance(files, list):
            files.append(_normalize_path(text))
    if current is not None and _commit_matches_focus(current, focus):
        commits.append(_compact_commit(current))
    return commits[: min(len(commits), 16)]


def _parse_commit_header(raw: str) -> dict[str, object]:
    body = raw[len(_COMMIT_HEADER_PREFIX):]
    parts = body.split("|", 2)
    sha = parts[0] if len(parts) >= 1 else ""
    ts = _safe_int(parts[1]) if len(parts) >= 2 else 0
    summary = parts[2] if len(parts) >= 3 else ""
    return {"sha": sha, "timestamp": ts, "summary": summary, "files": []}


def _commit_matches_focus(commit: dict[str, object], focus: set[str]) -> bool:
    if not focus:
        return True
    files = commit.get("files", [])
    if not isinstance(files, list):
        return False
    normalized = {
        _normalize_path(item)
        for item in files
        if isinstance(item, str) and item.strip()
    }
    return bool(normalized.intersection(focus))


def _compact_commit(commit: dict[str, object]) -> dict[str, object]:
    ts = _safe_int(commit.get("timestamp"))
    timestamp = (
        datetime.fromtimestamp(ts, tz=UTC).isoformat(timespec="seconds")
        if ts > 0
        else ""
    )
    files = commit.get("files", [])
    return {
        "sha": str(commit.get("sha", ""))[:12],
        "timestamp": timestamp,
        "summary": str(commit.get("summary", "")),
        "files": _string_list(files, limit=10),
    }


def _extract_touched_files(findings: list[object]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in findings:
        if not isinstance(item, dict):
            continue
        file_direct = item.get("file")
        if isinstance(file_direct, str) and file_direct.strip():
            normalized = _normalize_path(file_direct)
            if normalized not in seen:
                seen.add(normalized)
                out.append(normalized)

        related_files = item.get("related_files", [])
        if not isinstance(related_files, list):
            continue
        for rel in related_files:
            if not isinstance(rel, str) or not rel.strip():
                continue
            normalized = _normalize_path(rel)
            if normalized in seen:
                continue
            seen.add(normalized)
            out.append(normalized)
    return out


def _extract_dimensions(findings: list[object]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in findings:
        if not isinstance(item, dict):
            continue
        raw = item.get("dimension")
        if not isinstance(raw, str):
            continue
        dim = raw.strip()
        if not dim or dim in seen:
            continue
        seen.add(dim)
        out.append(dim)
    return out


def _normalize_path(raw: str) -> str:
    return raw.strip().replace("\\", "/").lstrip("./")


def _string_list(value: object, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text:
            continue
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _safe_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if text:
            try:
                return int(text)
            except ValueError:
                return 0
    return 0


def _git_output(repo_root: Path, args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


__all__ = [
    "build_incremental_review_memory",
    "record_review_import_memory",
    "review_memory_path",
]
