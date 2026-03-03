"""Metadata helpers for scorecard rendering."""

from __future__ import annotations

import logging
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)


def resolve_project_name(project_root: Path) -> str:
    """Resolve owner/repo display name from GitHub CLI, git remote, or folder."""
    try:
        name = subprocess.check_output(
            ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
            cwd=str(project_root),
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        ).strip()
        if "/" in name:
            return name
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ) as exc:
        logger.debug("gh repo view failed, falling back to git remote: %s", exc)

    try:
        url = subprocess.check_output(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=str(project_root),
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        ).strip()
        if url.startswith("git@") and ":" in url:
            path = url.split(":")[-1]
        else:
            path = "/".join(url.split("/")[-2:])
        return path.removesuffix(".git")
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        IndexError,
        subprocess.TimeoutExpired,
    ) as exc:
        logger.debug("git remote lookup failed, falling back to folder name: %s", exc)
        return project_root.name


def resolve_package_version(
    project_root: Path,
    *,
    version_getter: Callable[[str], str],
    package_not_found_error: type[Exception],
) -> str:
    """Resolve package version from installed metadata or local pyproject."""
    try:
        return version_getter("structorium")
    except package_not_found_error as exc:
        logger.debug("Package metadata lookup failed, trying pyproject.toml: %s", exc)

    pyproject_path = project_root / "pyproject.toml"
    try:
        text = pyproject_path.read_text(encoding="utf-8")
        match = re.search(r'^\s*version\s*=\s*"([^"]+)"\s*$', text, re.MULTILINE)
        if match:
            return match.group(1)
    except OSError as exc:
        logger.debug("Failed to read pyproject.toml for version: %s", exc)

    return "unknown"
