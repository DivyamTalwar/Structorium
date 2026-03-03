"""Import guards for deprecated compatibility facades."""

from __future__ import annotations

import ast
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE_ROOT = _PROJECT_ROOT
_ALLOWED_COMPAT_MODULES = {
    "utils.py",
    "file_discovery.py",
}


def _runtime_python_files() -> list[tuple[Path, str]]:
    files: list[tuple[Path, str]] = []
    for path in _PACKAGE_ROOT.rglob("*.py"):
        rel = path.relative_to(_PROJECT_ROOT).as_posix()
        if rel.startswith(
            (
                ".git/",
                ".venv/",
                ".mypy_cache/",
                ".ruff_cache/",
                ".pytest_cache/",
                ".import_linter_cache/",
                ".structorium/",
                "tmp/",
                "build/",
                "dist/",
                ".pkg-smoke/",
            )
        ):
            continue
        if rel.startswith("tests/") or "/tests/" in rel:
            continue
        if rel in _ALLOWED_COMPAT_MODULES:
            continue
        files.append((path, rel))
    return files


def _compat_import_violations(path: Path, rel: str) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    violations: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in {"utils", "file_discovery"}:
                    violations.append(f"{rel}:{node.lineno} import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module in {"utils", "file_discovery"}:
                violations.append(f"{rel}:{node.lineno} from {module} import ...")
    return violations


def test_runtime_code_avoids_deprecated_compat_facades():
    violations: list[str] = []
    for path, rel in _runtime_python_files():
        violations.extend(_compat_import_violations(path, rel))
    assert not violations, "runtime imports deprecated compat facades:\n" + "\n".join(
        sorted(violations)
    )
