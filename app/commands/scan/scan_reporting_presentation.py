"""Scan reporting: score breakdown, delta helpers, and detector progress."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

# ---------------------------------------------------------------------------
# Protocol stubs for dependency-injected modules
# ---------------------------------------------------------------------------


class _StateMod(Protocol):
    def path_scoped_findings(self, findings: dict, scan_path: object) -> dict: ...


class _NarrativeMod(Protocol):
    STRUCTURAL_MERGE: frozenset[str]


class _RegistryMod(Protocol):
    DETECTORS: dict

    def display_order(self) -> list[str]: ...


# ---------------------------------------------------------------------------
# Breakdown helpers (from scan_reporting_breakdown)
# ---------------------------------------------------------------------------


def dimension_bar(score: float, *, colorize_fn, bar_len: int = 15) -> str:
    """Render a score bar consistent with scan detector bars."""
    filled = max(0, min(bar_len, round(score / 100 * bar_len)))
    if score >= 98:
        return colorize_fn("█" * bar_len, "green")
    if score >= 93:
        return colorize_fn("█" * filled, "green") + colorize_fn(
            "░" * (bar_len - filled), "dim"
        )
    return colorize_fn("█" * filled, "yellow") + colorize_fn(
        "░" * (bar_len - filled), "dim"
    )


def show_score_model_breakdown(
    state: dict,
    *,
    scoring_mod,
    colorize_fn,
    dim_scores: dict | None = None,
) -> None:
    """Show score recipe and weighted drags."""
    if dim_scores is None:
        dim_scores = state.get("dimension_scores", {})
    if not dim_scores:
        return

    breakdown = scoring_mod.compute_health_breakdown(dim_scores)
    mech_frac = float(breakdown.get("mechanical_fraction", 1.0) or 0.0)
    subj_frac = float(breakdown.get("subjective_fraction", 0.0) or 0.0)
    mech_avg = float(breakdown.get("mechanical_avg", 100.0) or 100.0)
    subj_avg_raw = breakdown.get("subjective_avg")
    subj_avg = float(subj_avg_raw) if isinstance(subj_avg_raw, int | float) else None
    entries = [
        entry for entry in breakdown.get("entries", []) if isinstance(entry, dict)
    ]
    if not entries:
        return

    print(colorize_fn("  Score recipe:", "dim"))
    if subj_avg is None or subj_frac <= 0.0:
        print(colorize_fn("    overall = 100% mechanical", "dim"))
        print(colorize_fn(f"    Mechanical pool average: {mech_avg:.1f}%", "dim"))
    elif mech_frac <= 0.0:
        print(colorize_fn("    overall = 100% subjective", "dim"))
        print(colorize_fn(f"    Subjective pool average: {subj_avg:.1f}%", "dim"))
    else:
        print(
            colorize_fn(
                f"    overall = {mech_frac * 100:.0f}% mechanical + {subj_frac * 100:.0f}% subjective",
                "dim",
            )
        )
        print(
            colorize_fn(
                f"    Pool averages: mechanical {mech_avg:.1f}% · subjective {subj_avg:.1f}%",
                "dim",
            )
        )

    drags = sorted(
        [
            entry
            for entry in entries
            if float(entry.get("overall_drag", 0.0) or 0.0) > 0.01
        ],
        key=lambda entry: -float(entry.get("overall_drag", 0.0) or 0.0),
    )
    if drags:
        print(colorize_fn("    Biggest weighted drags:", "dim"))
        for entry in drags[:5]:
            name = str(entry.get("name", "unknown"))
            score = float(entry.get("score", 0.0) or 0.0)
            drag = float(entry.get("overall_drag", 0.0) or 0.0)
            pool = str(entry.get("pool", "unknown"))
            pool_share = float(entry.get("pool_share", 0.0) or 0.0) * 100
            print(
                colorize_fn(
                    f"      - {name}: -{drag:.2f} pts "
                    f"(score {score:.1f}%, {pool_share:.1f}% of {pool} pool)",
                    "dim",
                )
            )
    print()


def show_dimension_deltas(
    prev: dict,
    current: dict,
    *,
    scoring_mod,
    colorize_fn,
) -> None:
    """Show which dimensions changed between scans (health and strict)."""
    moved = []
    for dim in scoring_mod.DIMENSIONS:
        p = prev.get(dim.name, {})
        n = current.get(dim.name, {})
        if not p or not n:
            continue
        old_score = p.get("score", 100)
        new_score = n.get("score", 100)
        old_strict = p.get("strict", old_score)
        new_strict = n.get("strict", new_score)
        delta = new_score - old_score
        strict_delta = new_strict - old_strict
        if abs(delta) >= 0.1 or abs(strict_delta) >= 0.1:
            moved.append(
                (
                    dim.name,
                    old_score,
                    new_score,
                    delta,
                    old_strict,
                    new_strict,
                    strict_delta,
                )
            )

    if not moved:
        return

    print(colorize_fn("  Moved:", "dim"))
    for name, old, new, delta, old_s, new_s, s_delta in sorted(
        moved, key=lambda item: item[3]
    ):
        sign = "+" if delta > 0 else ""
        color = "green" if delta > 0 else "red"
        strict_str = ""
        if abs(s_delta) >= 0.1:
            s_sign = "+" if s_delta > 0 else ""
            strict_str = colorize_fn(
                f"  strict: {old_s:.1f}→{new_s:.1f}% ({s_sign}{s_delta:.1f}%)",
                "dim",
            )
        print(
            colorize_fn(
                f"    {name:<22} {old:.1f}% → {new:.1f}%  ({sign}{delta:.1f}%)", color
            )
            + strict_str
        )
    print()


def show_low_dimension_hints(
    dim_scores: dict,
    *,
    scoring_mod,
    colorize_fn,
) -> None:
    """Show actionable hints for dimensions below 50%."""
    static_names = {dim.name for dim in scoring_mod.DIMENSIONS}

    mechanical_hints = {
        "File health": "run `structorium show structural` — split large files",
        "Code quality": "run `structorium show smells` — fix code smells",
        "Duplication": "run `structorium show dupes` — deduplicate functions",
        "Test health": "add tests for uncovered files: `structorium show test_coverage`",
        "Security": "run `structorium show security` — fix security issues",
    }

    low = []
    for name, data in dim_scores.items():
        strict = data.get("strict", data.get("score", 100))
        if strict < 50:
            hint = (
                mechanical_hints.get(name, "run `structorium show` for details")
                if name in static_names
                else "run `structorium review --run-batches --runner codex --parallel --scan-after-import` to assess"
            )
            low.append((name, strict, hint))

    if not low:
        return

    low.sort(key=lambda item: item[1])
    print(colorize_fn("  Needs attention:", "yellow"))
    for name, score, hint in low:
        print(colorize_fn(f"    {name} ({score:.0f}%) — {hint}", "yellow"))
    print()


# ---------------------------------------------------------------------------
# Detector progress (from scan_reporting_progress)
# ---------------------------------------------------------------------------


def show_detector_progress(
    state: dict,
    *,
    state_mod: _StateMod,
    narrative_mod: _NarrativeMod,
    registry_mod: _RegistryMod,
    colorize_fn: Callable[[str, str], str],
) -> None:
    """Show per-detector progress bars."""
    findings = state_mod.path_scoped_findings(state["findings"], state.get("scan_path"))
    if not findings:
        return

    by_detector: dict[str, dict] = {}
    for finding in findings.values():
        detector = finding.get("detector", "unknown")
        if detector in narrative_mod.STRUCTURAL_MERGE:
            detector = "structural"
        if detector not in by_detector:
            by_detector[detector] = {"open": 0, "total": 0}
        by_detector[detector]["total"] += 1
        if finding["status"] == "open":
            by_detector[detector]["open"] += 1

    detector_order = [
        registry_mod.DETECTORS[d].display
        for d in registry_mod.display_order()
        if d in registry_mod.DETECTORS
    ]
    order_map = {display: i for i, display in enumerate(detector_order)}
    sorted_dets = sorted(by_detector.items(), key=lambda item: order_map.get(item[0], 99))

    print(colorize_fn("  Detector progress (open findings by detector):", "dim"))
    print(colorize_fn("  " + "─" * 50, "dim"))
    bar_len = 15
    for detector, data in sorted_dets:
        total = data["total"]
        open_count = data["open"]
        addressed = total - open_count
        pct = round(addressed / total * 100) if total else 100

        filled = round(pct / 100 * bar_len)
        if pct == 100:
            bar = colorize_fn("█" * bar_len, "green")
        elif open_count <= 2:
            bar = colorize_fn("█" * filled, "green") + colorize_fn(
                "░" * (bar_len - filled), "dim"
            )
        else:
            bar = colorize_fn("█" * filled, "yellow") + colorize_fn(
                "░" * (bar_len - filled), "dim"
            )

        det_label = detector.replace("_", " ").ljust(18)
        open_str = (
            colorize_fn(f"{open_count:3d} open", "yellow")
            if open_count > 0
            else colorize_fn("  ✓", "green")
        )
        print(
            f"  {det_label} {bar} {pct:3d}%  {open_str}  {colorize_fn(f'/ {total}', 'dim')}"
        )

    print()


__all__ = [
    "dimension_bar",
    "show_dimension_deltas",
    "show_detector_progress",
    "show_low_dimension_hints",
    "show_score_model_breakdown",
]
