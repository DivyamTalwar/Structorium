"""Detector/fixer factory helpers for generic language plugins."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

from languages._framework.base.types import (
    DetectorPhase,
    FixerConfig,
    FixResult,
)
from languages._framework.generic_parts.parsers import PARSERS
from languages._framework.generic_parts.tool_runner import (
    SubprocessRun,
    ToolRunResult,
    resolve_command_argv,
    run_tool,
    run_tool_result,
)
from languages._framework.generic_parts.tool_spec import ToolSpec
from state import make_finding


def _record_tool_failure_coverage(
    lang: object,
    *,
    detector: str,
    label: str,
    result: ToolRunResult,
) -> None:
    """Attach reduced-coverage metadata when generic detector tooling fails."""
    if result.status != "error":
        return

    record = {
        "detector": detector,
        "status": "reduced",
        "confidence": 0.0,
        "summary": f"{label} tooling unavailable ({result.error_kind or 'error'})",
        "impact": "Detector results may be under-reported for this scan.",
        "remediation": "Install/fix the tool command and rerun scan.",
        "tool": label,
        "reason": result.error_kind or "tool_error",
    }
    detector_coverage = getattr(lang, "detector_coverage", None)
    if isinstance(detector_coverage, dict):
        detector_coverage[detector] = dict(record)

    coverage_warnings = getattr(lang, "coverage_warnings", None)
    if isinstance(coverage_warnings, list):
        if not any(
            isinstance(entry, dict) and entry.get("detector") == detector
            for entry in coverage_warnings
        ):
            coverage_warnings.append(dict(record))


def make_tool_phase(
    label: str,
    cmd: str,
    fmt: str,
    smell_id: str,
    tier: int,
) -> DetectorPhase:
    """Create a DetectorPhase that runs an external tool and parses output."""
    parser = PARSERS[fmt]

    def run(path: Path, lang: object) -> tuple[list, dict]:
        run_result = run_tool_result(cmd, path, parser)
        if run_result.status == "error":
            _record_tool_failure_coverage(
                lang,
                detector=smell_id,
                label=label,
                result=run_result,
            )
            return [], {}
        entries = list(run_result.entries)
        if not entries:
            return [], {}
        findings = [
            make_finding(
                smell_id,
                entry["file"],
                f"{smell_id}::{entry['line']}",
                tier=tier,
                confidence="medium",
                summary=entry["message"],
            )
            for entry in entries
        ]
        return findings, {smell_id: len(entries)}

    return DetectorPhase(label, run)


def make_detect_fn(
    cmd: str,
    parser: Callable[[str, Path], list[dict]],
    *,
    run_subprocess: SubprocessRun | None = None,
) -> Callable:
    """Create detect function that runs a tool with an optional injected runner."""
    def detect(path, **kwargs):
        del kwargs
        return run_tool(cmd, path, parser, run_subprocess=run_subprocess)

    return detect


def make_generic_fixer(
    tool: ToolSpec,
    *,
    run_subprocess: SubprocessRun | None = None,
) -> FixerConfig:
    """Create a FixerConfig from a tool spec with an optional injected runner."""
    smell_id = tool["id"]
    fix_cmd = tool["fix_cmd"]
    if fix_cmd is None:
        raise ValueError("make_generic_fixer requires tool['fix_cmd'] to be provided")
    detect = make_detect_fn(
        tool["cmd"],
        PARSERS[tool["fmt"]],
        run_subprocess=run_subprocess,
    )

    def fix(entries, dry_run=False, path=None, **kwargs):
        del kwargs
        if dry_run or not path:
            return FixResult(entries=[{"file": e["file"], "line": e["line"]} for e in entries])
        runner = run_subprocess or subprocess.run
        try:
            runner(
                resolve_command_argv(fix_cmd),
                shell=False,
                cwd=str(path),
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return FixResult(entries=[], skip_reasons={"tool_unavailable": len(entries)})
        remaining = detect(path)
        fixed_count = max(0, len(entries) - len(remaining))
        return FixResult(
            entries=[{"file": e["file"], "fixed": True} for e in entries[:fixed_count]]
        )

    return FixerConfig(
        label=f"Fix {tool['label']} issues",
        detect=detect,
        fix=fix,
        detector=smell_id,
        verb="Fixed",
        dry_verb="Would fix",
    )


# Backwards-compatible aliases for historical import sites.
make_detect_fn_with_runner = make_detect_fn
make_generic_fixer_with_runner = make_generic_fixer


__all__ = [
    "make_detect_fn",
    "make_detect_fn_with_runner",
    "make_generic_fixer",
    "make_generic_fixer_with_runner",
    "make_tool_phase",
]
