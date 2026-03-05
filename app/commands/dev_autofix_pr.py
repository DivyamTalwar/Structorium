"""Autofix PR planning helpers for `structorium dev autofix-pr`."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.commands.helpers.lang import resolve_lang
from app.commands.helpers.runtime import command_runtime
from core._internal.text_utils import get_project_root
from core.discovery_api import safe_write_text
from core.output_api import colorize

_TIER_RISK_WEIGHT = {1: 10.0, 2: 5.0, 3: 2.0, 4: 1.0}


@dataclass(frozen=True)
class _FixCandidate:
    detector: str
    fixers: tuple[str, ...]
    finding_count: int
    weighted_risk_delta: float
    highest_tier: int


def cmd_dev_autofix_pr(args) -> None:
    """Build (and optionally execute) a local autofix PR plan."""
    runtime = command_runtime(args)
    state = runtime.state if isinstance(runtime.state, dict) else {}
    lang = resolve_lang(args)
    if not lang:
        raise SystemExit(colorize("Could not detect language. Use --lang.", "red"))

    detector_to_fixers = _detector_to_fixers(getattr(lang, "fixers", {}))
    if not detector_to_fixers:
        print(colorize("No fixers registered for the selected language.", "yellow"))
        return

    candidates = _collect_candidates(state, detector_to_fixers)
    if not candidates:
        print(colorize("No open findings currently eligible for autofix.", "green"))
        return

    max_fixers = _coerce_positive_int(getattr(args, "max_fixers", None), default=3)
    risk_threshold = _coerce_non_negative_float(
        getattr(args, "risk_threshold", None),
        default=12.0,
    )
    selected = _select_candidates(
        candidates,
        max_fixers=max_fixers,
        risk_threshold=risk_threshold,
    )
    total_risk_delta = round(sum(item.weighted_risk_delta for item in selected), 2)
    plan_md = _render_plan_markdown(
        selected=selected,
        all_candidates=candidates,
        lang_name=str(getattr(lang, "name", "unknown")),
        risk_threshold=risk_threshold,
        total_risk_delta=total_risk_delta,
        branch_name=_branch_name(getattr(args, "branch_prefix", "autofix")),
        base_ref=str(getattr(args, "base_ref", "main") or "main"),
    )

    project_root = get_project_root()
    plan_path = project_root / ".structorium" / "autofix_pr_plan.md"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    safe_write_text(plan_path, plan_md)

    print(colorize("Autofix PR planner:", "bold"))
    print(colorize(f"  Candidates: {len(candidates)}", "dim"))
    print(colorize(f"  Selected: {len(selected)}", "dim"))
    print(colorize(f"  Estimated risk delta: {total_risk_delta}", "dim"))
    print(colorize(f"  Plan file: {plan_path}", "dim"))

    if not bool(getattr(args, "execute", False)):
        print(
            colorize(
                "  Dry mode only. Re-run with --execute to run selected fixers locally.",
                "yellow",
            )
        )
        return

    branch_name = _branch_name(getattr(args, "branch_prefix", "autofix"))
    if bool(getattr(args, "create_branch", False)):
        _create_branch(project_root=project_root, branch_name=branch_name)

    _execute_fixers(
        selected=selected,
        project_root=project_root,
        scan_path=str(getattr(args, "path", "") or "."),
    )


def _detector_to_fixers(fixers: object) -> dict[str, list[str]]:
    if not isinstance(fixers, dict):
        return {}
    mapping: dict[str, list[str]] = {}
    for fixer_name, cfg in fixers.items():
        detector = getattr(cfg, "detector", None)
        if not isinstance(detector, str) or not detector.strip():
            continue
        name = str(fixer_name).strip()
        if not name:
            continue
        mapping.setdefault(detector, []).append(name)
    for values in mapping.values():
        values.sort()
    return mapping


def _collect_candidates(
    state: dict[str, Any],
    detector_to_fixers: dict[str, list[str]],
) -> list[_FixCandidate]:
    findings = state.get("findings", {})
    if not isinstance(findings, dict):
        findings = {}

    by_detector_count: dict[str, int] = {}
    by_detector_risk: dict[str, float] = {}
    by_detector_best_tier: dict[str, int] = {}

    for payload in findings.values():
        if not isinstance(payload, dict):
            continue
        if str(payload.get("status", "open")) != "open":
            continue
        detector = str(payload.get("detector", "")).strip()
        if not detector or detector not in detector_to_fixers:
            continue
        tier = _safe_tier(payload.get("tier"))
        by_detector_count[detector] = by_detector_count.get(detector, 0) + 1
        by_detector_risk[detector] = by_detector_risk.get(detector, 0.0) + _TIER_RISK_WEIGHT.get(
            tier,
            1.0,
        )
        by_detector_best_tier[detector] = min(
            by_detector_best_tier.get(detector, tier),
            tier,
        )

    candidates: list[_FixCandidate] = []
    for detector, count in by_detector_count.items():
        candidates.append(
            _FixCandidate(
                detector=detector,
                fixers=tuple(detector_to_fixers.get(detector, [])),
                finding_count=count,
                weighted_risk_delta=round(by_detector_risk.get(detector, 0.0), 2),
                highest_tier=by_detector_best_tier.get(detector, 4),
            )
        )
    candidates.sort(
        key=lambda item: (
            -item.weighted_risk_delta,
            item.highest_tier,
            item.detector,
        )
    )
    return candidates


def _select_candidates(
    candidates: list[_FixCandidate],
    *,
    max_fixers: int,
    risk_threshold: float,
) -> list[_FixCandidate]:
    selected: list[_FixCandidate] = []
    risk_total = 0.0
    for item in candidates:
        if len(selected) >= max_fixers:
            break
        selected.append(item)
        risk_total += item.weighted_risk_delta
        if risk_total >= risk_threshold and selected:
            break
    return selected


def _render_plan_markdown(
    *,
    selected: list[_FixCandidate],
    all_candidates: list[_FixCandidate],
    lang_name: str,
    risk_threshold: float,
    total_risk_delta: float,
    branch_name: str,
    base_ref: str,
) -> str:
    now = datetime.now(UTC).isoformat(timespec="seconds")
    lines: list[str] = []
    lines.append("# Autofix PR Plan")
    lines.append("")
    lines.append(f"- Generated: `{now}`")
    lines.append(f"- Language: `{lang_name}`")
    lines.append(f"- Base ref: `{base_ref}`")
    lines.append(f"- Proposed branch: `{branch_name}`")
    lines.append(f"- Risk threshold: `{risk_threshold}`")
    lines.append(f"- Selected estimated risk delta: `{total_risk_delta}`")
    lines.append("")
    lines.append("## Selected Fixers")
    lines.append("")
    if not selected:
        lines.append("_No candidates selected._")
    else:
        for item in selected:
            primary = item.fixers[0] if item.fixers else "(none)"
            lines.append(
                "- "
                f"`{primary}` for detector `{item.detector}` "
                f"(open={item.finding_count}, highest_tier=T{item.highest_tier}, "
                f"risk_delta={item.weighted_risk_delta})"
            )
    lines.append("")
    lines.append("## Full Candidate Backlog")
    lines.append("")
    for item in all_candidates:
        fixers = ", ".join(f"`{name}`" for name in item.fixers) if item.fixers else "`(none)`"
        lines.append(
            "- "
            f"detector `{item.detector}` -> {fixers} "
            f"(open={item.finding_count}, highest_tier=T{item.highest_tier}, "
            f"risk_delta={item.weighted_risk_delta})"
        )
    lines.append("")
    lines.append("## Suggested PR Metadata")
    lines.append("")
    lines.append(f"- Branch: `{branch_name}`")
    lines.append("- Title: `fix(autofix): reduce open mechanical debt with gated fixer batch`")
    lines.append("- Body highlights:")
    lines.append("  - automated deterministic fixer run")
    lines.append("  - risk-threshold based selection")
    lines.append("  - no manual semantic rewrites")
    lines.append("  - follow-up scan + tests required")
    lines.append("")
    lines.append("## Suggested Commands")
    lines.append("")
    lines.append("```bash")
    lines.append(f"git checkout -b {branch_name}")
    for item in selected:
        if item.fixers:
            lines.append(f"python -m structorium fix {item.fixers[0]} --path .")
    lines.append("python -m structorium scan --profile ci")
    lines.append("pytest -q")
    lines.append("```")
    lines.append("")
    return "\n".join(lines) + "\n"


def _branch_name(prefix: object) -> str:
    safe_prefix = str(prefix or "autofix").strip().replace(" ", "-") or "autofix"
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"{safe_prefix}/batch-{stamp}"


def _create_branch(*, project_root: Path, branch_name: str) -> None:
    result = subprocess.run(
        ["git", "-C", str(project_root), "checkout", "-b", branch_name],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "unknown git error"
        raise SystemExit(colorize(f"Unable to create branch `{branch_name}`: {message}", "red"))
    print(colorize(f"  Created branch: {branch_name}", "green"))


def _execute_fixers(
    *,
    selected: list[_FixCandidate],
    project_root: Path,
    scan_path: str,
) -> None:
    if not selected:
        print(colorize("No selected fixers to execute.", "yellow"))
        return
    for item in selected:
        if not item.fixers:
            continue
        fixer = item.fixers[0]
        cmd = [sys.executable, "-m", "structorium", "fix", fixer, "--path", scan_path]
        print(colorize(f"  Running: {' '.join(cmd)}", "dim"))
        result = subprocess.run(
            cmd,
            cwd=str(project_root),
            check=False,
            timeout=45 * 60,
        )
        if result.returncode != 0:
            raise SystemExit(
                colorize(f"Fixer `{fixer}` failed with exit code {result.returncode}.", "red")
            )
    print(colorize("  Autofix execution completed.", "green"))


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
    if tier < 1:
        return 1
    if tier > 4:
        return 4
    return tier


def _coerce_positive_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, float):
        parsed = int(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            parsed = int(text)
        except ValueError:
            return default
    else:
        return default
    try:
        parsed = int(parsed)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _coerce_non_negative_float(value: object, *, default: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, int | float):
        parsed = float(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            parsed = float(text)
        except ValueError:
            return default
    else:
        return default
    try:
        parsed = float(parsed)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


__all__ = ["cmd_dev_autofix_pr"]
