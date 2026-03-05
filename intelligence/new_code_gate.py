"""New-code-only architecture gate for PR/CI workflows."""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_BOOL_TRUE = {"1", "true", "yes", "on"}
_BOOL_FALSE = {"0", "false", "no", "off"}
_DIFF_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
_LINE_HINT_KEYS = (
    "line",
    "line_number",
    "line_no",
    "lineno",
    "start_line",
    "row",
)
_DEFAULT_BASE_REF_CANDIDATES = ("origin/main", "main", "HEAD~1")


@dataclass(frozen=True)
class NewCodeGatePolicy:
    """Policy thresholds used by the new-code gate."""

    name: str
    max_new_findings: int
    max_new_high: int
    max_new_critical: int
    blocked_detectors: tuple[str, ...] = ()


@dataclass(frozen=True)
class NewCodeGateSettings:
    """Resolved runtime settings for new-code gate evaluation."""

    enabled: bool
    base_ref: str
    policy: NewCodeGatePolicy


@dataclass(frozen=True)
class NewCodeGateFinding:
    """A finding that was classified as belonging to new code."""

    finding_id: str
    detector: str
    file: str
    tier: int
    summary: str
    line: int | None


@dataclass(frozen=True)
class NewCodeGateResult:
    """Evaluation output for new-code gate status."""

    enabled: bool
    policy_name: str
    base_ref: str
    changed_files: int
    changed_line_ranges: int
    new_findings: int
    new_high: int
    new_critical: int
    blocked_detector_hits: int
    passed: bool
    findings: tuple[NewCodeGateFinding, ...]
    warnings: tuple[str, ...] = ()


_POLICIES: dict[str, NewCodeGatePolicy] = {
    "strict": NewCodeGatePolicy(
        name="strict",
        max_new_findings=0,
        max_new_high=0,
        max_new_critical=0,
        blocked_detectors=("security", "layer_violation", "private_imports"),
    ),
    "standard": NewCodeGatePolicy(
        name="standard",
        max_new_findings=3,
        max_new_high=0,
        max_new_critical=0,
        blocked_detectors=("security",),
    ),
    "ai_generated_code": NewCodeGatePolicy(
        name="ai_generated_code",
        max_new_findings=1,
        max_new_high=0,
        max_new_critical=0,
        blocked_detectors=(
            "security",
            "layer_violation",
            "private_imports",
            "coupling",
        ),
    ),
}


def resolve_new_code_gate_settings(
    config: dict[str, Any] | None,
    *,
    profile: str | None = None,
    env: dict[str, str] | None = None,
) -> NewCodeGateSettings:
    """Resolve gate settings from config + environment variables."""
    cfg = config if isinstance(config, dict) else {}
    source_env = env if env is not None else os.environ

    enabled = _coerce_bool(
        source_env.get("STRUCTORIUM_NEW_CODE_GATE_ENABLED"),
        default=_coerce_bool(cfg.get("new_code_gate_enabled"), default=False),
    )
    if not enabled and profile == "ci":
        enabled = _coerce_bool(
            source_env.get("STRUCTORIUM_NEW_CODE_GATE_ON_CI"),
            default=False,
        )

    policy_name_raw = str(
        source_env.get(
            "STRUCTORIUM_NEW_CODE_GATE_POLICY",
            cfg.get("new_code_gate_policy", "standard"),
        )
    ).strip()
    policy_name = _normalize_policy_name(policy_name_raw)
    base_ref = str(
        source_env.get(
            "STRUCTORIUM_NEW_CODE_GATE_BASE_REF",
            cfg.get("new_code_gate_base_ref", "origin/main"),
        )
    ).strip() or "origin/main"

    policy = _POLICIES.get(policy_name, _POLICIES["standard"])
    policy = _policy_with_overrides(policy, cfg=cfg, source_env=source_env)

    return NewCodeGateSettings(enabled=enabled, base_ref=base_ref, policy=policy)


def evaluate_new_code_gate(
    *,
    state: dict[str, Any],
    repo_root: Path,
    settings: NewCodeGateSettings,
    scan_path: str | None = None,
) -> NewCodeGateResult:
    """Evaluate new-code gate against open findings in state."""
    if not settings.enabled:
        return NewCodeGateResult(
            enabled=False,
            policy_name=settings.policy.name,
            base_ref=settings.base_ref,
            changed_files=0,
            changed_line_ranges=0,
            new_findings=0,
            new_high=0,
            new_critical=0,
            blocked_detector_hits=0,
            passed=True,
            findings=(),
        )

    changed_lines, warnings = _changed_lines_by_file(
        repo_root=repo_root,
        base_ref=settings.base_ref,
    )
    if not changed_lines:
        return NewCodeGateResult(
            enabled=True,
            policy_name=settings.policy.name,
            base_ref=settings.base_ref,
            changed_files=0,
            changed_line_ranges=0,
            new_findings=0,
            new_high=0,
            new_critical=0,
            blocked_detector_hits=0,
            passed=True,
            findings=(),
            warnings=warnings,
        )

    findings_map = state.get("findings", {})
    if not isinstance(findings_map, dict):
        findings_map = {}

    normalized_scan_path = _normalize_scan_path(scan_path)
    new_code_findings: list[NewCodeGateFinding] = []
    for finding_id, payload in findings_map.items():
        if not isinstance(payload, dict):
            continue
        if str(payload.get("status", "open")) != "open":
            continue
        file_path = _normalize_finding_path(str(payload.get("file", "")), repo_root)
        if not file_path:
            continue
        if normalized_scan_path and not _path_in_scope(file_path, normalized_scan_path):
            continue
        ranges = changed_lines.get(file_path)
        if ranges is None:
            continue
        line = _extract_line_hint(payload.get("detail"))
        if line is not None and not _line_in_ranges(line, ranges):
            continue
        if line is None and len(ranges) == 0:
            # Pure rename/deletion contexts with no new added lines are ignored.
            continue
        tier = _safe_tier(payload.get("tier"))
        detector = str(payload.get("detector", "unknown")).strip() or "unknown"
        summary = str(payload.get("summary", "")).strip()
        new_code_findings.append(
            NewCodeGateFinding(
                finding_id=str(finding_id),
                detector=detector,
                file=file_path,
                tier=tier,
                summary=summary,
                line=line,
            )
        )

    new_code_findings.sort(
        key=lambda item: (
            item.tier,
            item.detector,
            item.file,
            item.finding_id,
        )
    )
    new_findings = len(new_code_findings)
    new_high = sum(1 for item in new_code_findings if item.tier <= 2)
    new_critical = sum(1 for item in new_code_findings if item.tier <= 1)
    blocked_detector_set = set(settings.policy.blocked_detectors)
    blocked_detector_hits = sum(
        1 for item in new_code_findings if item.detector in blocked_detector_set
    )

    passed = (
        _threshold_ok(new_findings, settings.policy.max_new_findings)
        and _threshold_ok(new_high, settings.policy.max_new_high)
        and _threshold_ok(new_critical, settings.policy.max_new_critical)
        and blocked_detector_hits == 0
    )
    changed_line_ranges = sum(len(ranges) for ranges in changed_lines.values())
    return NewCodeGateResult(
        enabled=True,
        policy_name=settings.policy.name,
        base_ref=settings.base_ref,
        changed_files=len(changed_lines),
        changed_line_ranges=changed_line_ranges,
        new_findings=new_findings,
        new_high=new_high,
        new_critical=new_critical,
        blocked_detector_hits=blocked_detector_hits,
        passed=passed,
        findings=tuple(new_code_findings),
        warnings=warnings,
    )


def render_new_code_gate_report(result: NewCodeGateResult) -> list[tuple[str, str]]:
    """Render terminal lines for gate report as (line, color_style)."""
    if not result.enabled:
        return []

    lines: list[tuple[str, str]] = []
    headline = (
        "  New-code gate: PASS"
        if result.passed
        else "  New-code gate: FAIL (merge-blocking)"
    )
    lines.append((headline, "green" if result.passed else "red"))
    lines.append(
        (
            "    "
            f"policy={result.policy_name} "
            f"base_ref={result.base_ref} "
            f"changed_files={result.changed_files} "
            f"changed_hunks={result.changed_line_ranges}",
            "dim",
        )
    )
    lines.append(
        (
            "    "
            f"new_findings={result.new_findings} "
            f"new_high={result.new_high} "
            f"new_critical={result.new_critical} "
            f"blocked_detector_hits={result.blocked_detector_hits}",
            "dim",
        )
    )
    for warning in result.warnings:
        lines.append((f"    warning: {warning}", "yellow"))

    if result.findings:
        lines.append(("    top new-code findings:", "yellow" if not result.passed else "dim"))
        for item in result.findings[:8]:
            location = f"{item.file}:{item.line}" if item.line is not None else item.file
            lines.append(
                (
                    "      "
                    f"[T{item.tier}] {item.detector} :: {location} :: {item.summary}",
                    "dim",
                )
            )
        remaining = len(result.findings) - min(len(result.findings), 8)
        if remaining > 0:
            lines.append((f"      ... +{remaining} more", "dim"))
    return lines


def _normalize_policy_name(raw: str) -> str:
    normalized = raw.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in _POLICIES:
        return normalized
    return "standard"


def _policy_with_overrides(
    policy: NewCodeGatePolicy,
    *,
    cfg: dict[str, Any],
    source_env: Mapping[str, str],
) -> NewCodeGatePolicy:
    max_new_findings = _resolve_threshold_override(
        source_env.get(
            "STRUCTORIUM_NEW_CODE_GATE_MAX_NEW_FINDINGS",
            cfg.get("new_code_gate_max_new_findings"),
        ),
        policy_default=policy.max_new_findings,
    )
    max_new_high = _resolve_threshold_override(
        source_env.get(
            "STRUCTORIUM_NEW_CODE_GATE_MAX_NEW_HIGH",
            cfg.get("new_code_gate_max_new_high"),
        ),
        policy_default=policy.max_new_high,
    )
    max_new_critical = _resolve_threshold_override(
        source_env.get(
            "STRUCTORIUM_NEW_CODE_GATE_MAX_NEW_CRITICAL",
            cfg.get("new_code_gate_max_new_critical"),
        ),
        policy_default=policy.max_new_critical,
    )
    return NewCodeGatePolicy(
        name=policy.name,
        max_new_findings=max_new_findings,
        max_new_high=max_new_high,
        max_new_critical=max_new_critical,
        blocked_detectors=policy.blocked_detectors,
    )


def _coerce_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _BOOL_TRUE:
            return True
        if normalized in _BOOL_FALSE:
            return False
    return default


def _coerce_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return default
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
                return default
    return default


def _resolve_threshold_override(raw: object, *, policy_default: int) -> int:
    """Resolve optional threshold override where -1 means 'use policy default'."""
    parsed = _coerce_int(raw, default=-1)
    if parsed < 0:
        return policy_default
    return parsed


def _threshold_ok(value: int, threshold: int) -> bool:
    return threshold < 0 or value <= threshold


def _changed_lines_by_file(
    *,
    repo_root: Path,
    base_ref: str,
) -> tuple[dict[str, list[tuple[int, int]]], tuple[str, ...]]:
    resolved_base, warning = _resolve_base_ref(repo_root, base_ref)
    if resolved_base is None:
        return {}, (warning,) if warning else ("unable to resolve base ref",)

    patch = _git_output(
        repo_root,
        [
            "diff",
            "--unified=0",
            "--no-color",
            "--diff-filter=AMCR",
            f"{resolved_base}...HEAD",
        ],
    )
    if patch is None:
        return {}, ("unable to compute git diff for new-code gate",)
    return _parse_changed_lines(patch), ((warning,) if warning else ())


def _resolve_base_ref(repo_root: Path, base_ref: str) -> tuple[str | None, str | None]:
    candidates = [base_ref, *_DEFAULT_BASE_REF_CANDIDATES]
    seen: set[str] = set()
    for candidate in candidates:
        text = candidate.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        if _git_ref_exists(repo_root, text):
            warning = None if text == base_ref else f"base_ref {base_ref!r} not found; using {text!r}"
            return text, warning
    return None, f"base_ref {base_ref!r} not found"


def _git_ref_exists(repo_root: Path, ref: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--verify", "--quiet", ref],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


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


def _parse_changed_lines(diff_text: str) -> dict[str, list[tuple[int, int]]]:
    changed: dict[str, list[tuple[int, int]]] = {}
    current_file = ""
    for raw_line in diff_text.splitlines():
        if raw_line.startswith("+++ b/"):
            current_file = raw_line[6:].strip()
            changed.setdefault(current_file, [])
            continue
        if not current_file:
            continue
        match = _DIFF_HUNK_RE.match(raw_line)
        if not match:
            continue
        start = int(match.group(1))
        count = int(match.group(2) or "1")
        if count <= 0:
            continue
        changed[current_file].append((start, start + count - 1))
    return changed


def _normalize_scan_path(scan_path: str | None) -> str | None:
    if not isinstance(scan_path, str):
        return None
    text = scan_path.strip().replace("\\", "/").strip("/")
    if not text or text == ".":
        return None
    return text


def _path_in_scope(path: str, scan_path: str) -> bool:
    return path == scan_path or path.startswith(f"{scan_path}/")


def _normalize_finding_path(raw: str, repo_root: Path) -> str:
    if not raw:
        return ""
    candidate = Path(raw)
    if candidate.is_absolute():
        try:
            return candidate.resolve().relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            return candidate.as_posix()
    return raw.replace("\\", "/").strip()


def _extract_line_hint(detail: object) -> int | None:
    if not isinstance(detail, dict):
        return None
    for key in _LINE_HINT_KEYS:
        if key not in detail:
            continue
        value = detail.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int | float):
            number = int(value)
            if number > 0:
                return number
            continue
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.isdigit():
                number = int(stripped)
                if number > 0:
                    return number
    return None


def _line_in_ranges(line: int, ranges: list[tuple[int, int]]) -> bool:
    for start, end in ranges:
        if start <= line <= end:
            return True
    return False


def _safe_tier(value: object) -> int:
    if isinstance(value, bool):
        return 4
    if isinstance(value, int):
        tier = value
    elif isinstance(value, float):
        tier = int(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return 4
        try:
            tier = int(text)
        except ValueError:
            return 4
    else:
        return 4
    try:
        tier = int(tier)
    except (TypeError, ValueError):
        return 4
    if tier < 1:
        return 1
    if tier > 4:
        return 4
    return tier


__all__ = [
    "NewCodeGateFinding",
    "NewCodeGatePolicy",
    "NewCodeGateResult",
    "NewCodeGateSettings",
    "evaluate_new_code_gate",
    "render_new_code_gate_report",
    "resolve_new_code_gate_settings",
]
