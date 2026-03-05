"""Temporal coupling analysis from git history for ripple-risk detection."""

from __future__ import annotations

import subprocess
from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

_COMMIT_HEADER_PREFIX = "__C__"


@dataclass(frozen=True)
class _Commit:
    sha: str
    files: tuple[str, ...]


def compute_temporal_coupling(
    *,
    repo_root: Path,
    focus_files: list[str],
    max_commits: int,
    max_hotspots: int = 12,
) -> dict[str, object]:
    """Compute co-change hotspots and ripple scores for focus files."""
    commits = _read_recent_commits(repo_root=repo_root, max_commits=max_commits)
    if commits is None:
        return {"status": "unavailable", "reason": "git_history_unavailable"}
    if not commits:
        return {"status": "empty", "window_commits": 0, "hotspots": [], "ripple_files": []}

    focus = {_normalize_path(path) for path in focus_files if isinstance(path, str) and path}
    churn = Counter[str]()
    pair_counts = Counter[tuple[str, str]]()
    for commit in commits:
        files = tuple(sorted(set(commit.files)))
        for file_path in files:
            churn[file_path] += 1
        # Prevent quadratic blowups on very large commits.
        if len(files) > 40:
            files = files[:40]
        for left, right in combinations(files, 2):
            pair_counts[(left, right)] += 1

    if not focus:
        focus = {file_path for file_path, _ in churn.most_common(6)}

    hotspots: list[dict[str, object]] = []
    ripple_scores = Counter[str]()
    neighbor_index: dict[str, list[str]] = {}
    for (left, right), count in pair_counts.most_common():
        if count < 2:
            continue
        if focus and left not in focus and right not in focus:
            continue
        hotspots.append(
            {
                "left": left,
                "right": right,
                "co_change_commits": int(count),
                "left_churn": int(churn.get(left, 0)),
                "right_churn": int(churn.get(right, 0)),
            }
        )
        ripple_scores[left] += count
        ripple_scores[right] += count
        neighbor_index.setdefault(left, []).append(right)
        neighbor_index.setdefault(right, []).append(left)
        if len(hotspots) >= max_hotspots:
            break

    ripple_files: list[dict[str, object]] = []
    for file_path, score in ripple_scores.most_common(10):
        ripple_files.append(
            {
                "file": file_path,
                "ripple_score": int(score),
                "neighbors": neighbor_index.get(file_path, [])[:6],
            }
        )

    return {
        "status": "ready",
        "window_commits": len(commits),
        "focus_files": sorted(focus),
        "hotspots": hotspots,
        "ripple_files": ripple_files,
    }


def _read_recent_commits(*, repo_root: Path, max_commits: int) -> list[_Commit] | None:
    raw = _git_output(
        repo_root,
        [
            "log",
            "--date-order",
            f"-n{max(1, max_commits)}",
            f"--pretty=format:{_COMMIT_HEADER_PREFIX}%H",
            "--name-only",
        ],
    )
    if raw is None:
        return None

    commits: list[_Commit] = []
    current_sha = ""
    current_files: list[str] = []
    for line in raw.splitlines():
        text = line.strip()
        if not text:
            continue
        if text.startswith(_COMMIT_HEADER_PREFIX):
            if current_sha:
                commits.append(
                    _Commit(
                        sha=current_sha,
                        files=tuple(
                            _normalize_path(path)
                            for path in current_files
                            if path.strip()
                        ),
                    )
                )
            current_sha = text[len(_COMMIT_HEADER_PREFIX):]
            current_files = []
            continue
        current_files.append(text)
    if current_sha:
        commits.append(
            _Commit(
                sha=current_sha,
                files=tuple(
                    _normalize_path(path)
                    for path in current_files
                    if path.strip()
                ),
            )
        )
    return commits


def _normalize_path(raw: str) -> str:
    return raw.strip().replace("\\", "/").lstrip("./")


def _git_output(repo_root: Path, args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=25,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


__all__ = ["compute_temporal_coupling"]
