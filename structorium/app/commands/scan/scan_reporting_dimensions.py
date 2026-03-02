"""Dimension and detector table reporting for scan command."""

from __future__ import annotations

from structorium import scoring as scoring_mod
from structorium import state as state_mod
from . import scan_reporting_presentation as presentation_mod
from structorium.app.commands.scan.scan_reporting_subjective import (
    SubjectiveFollowup,
    build_subjective_followup,
    flatten_cli_keys,
    show_subjective_paths,
    subjective_entries_for_dimension_keys,
    subjective_integrity_followup,
    subjective_integrity_notice_lines,
    subjective_rerun_command,
)
from structorium.engine.planning.scorecard_projection import (
    dimension_cli_key,
)
from structorium.engine.planning.scorecard_projection import (
    scorecard_dimension_cli_keys,
)
from structorium.engine.planning.scorecard_projection import (
    scorecard_dimension_rows,
)
from structorium.engine.planning.scorecard_projection import (
    scorecard_subjective_entries,
)
from structorium.core.output import colorize
from structorium.core import registry as registry_mod
from structorium.intelligence import narrative as narrative_mod


def show_detector_progress(state: dict):
    """Show per-detector progress bars — the heartbeat of a scan."""
    return presentation_mod.show_detector_progress(
        state,
        state_mod=state_mod,
        narrative_mod=narrative_mod,
        registry_mod=registry_mod,
        colorize_fn=colorize,
    )


def _dimension_bar(score: float, *, bar_len: int = 15) -> str:
    """Render a score bar consistent with scan detector bars."""
    return presentation_mod.dimension_bar(score, colorize_fn=colorize, bar_len=bar_len)


def scorecard_dimension_entries(
    state: dict,
    *,
    dim_scores: dict | None = None,
) -> list[dict]:
    """Return scorecard rows with presentation-friendly metadata."""
    rows = scorecard_dimension_rows(state, dim_scores=dim_scores)
    subjective_by_name = {
        entry["name"]: entry
        for entry in scorecard_subjective_entries(
            state,
            dim_scores=dim_scores,
        )
    }
    entries: list[dict] = []
    for name, data in rows:
        detectors = data.get("detectors", {})
        subjective_meta = subjective_by_name.get(name)
        is_subjective = subjective_meta is not None
        score = float(data.get("score", 0.0))
        strict = float(data.get("strict", score))
        issues = int(data.get("issues", 0))
        checks = int(data.get("checks", 0))
        placeholder = bool(subjective_meta.get("placeholder")) if subjective_meta else False
        not_scanned = bool(
            not is_subjective and not detectors and checks == 0
        )
        carried_forward = bool(
            not is_subjective and data.get("carried_forward")
        )
        dim_key = str(subjective_meta.get("dimension_key", "")) if subjective_meta else ""
        stale = bool(subjective_meta.get("stale")) if subjective_meta else False
        cli_keys = (
            list(subjective_meta.get("cli_keys", []))
            if subjective_meta
            else scorecard_dimension_cli_keys(name, data)
        )
        entries.append(
            {
                "name": name,
                "score": score,
                "strict": strict,
                "issues": issues,
                "checks": checks,
                "subjective": is_subjective,
                "placeholder": placeholder,
                "stale": stale,
                "dimension_key": dim_key,
                "not_scanned": not_scanned,
                "carried_forward": carried_forward,
                "cli_keys": cli_keys,
            }
        )
    return entries


def show_scorecard_subjective_measures(state: dict) -> None:
    """Show canonical scorecard dimensions only (mechanical + subjective)."""
    entries = scorecard_dimension_entries(state)
    if not entries:
        return

    print(colorize("  Scorecard dimensions (matches scorecard.png):", "dim"))
    for entry in entries:
        if entry.get("not_scanned"):
            print(
                "  "
                + f"{entry['name']:<18} "
                + colorize("─── skipped ───────────────────  (run without --skip-slow)", "yellow")
            )
            continue
        bar = _dimension_bar(entry["score"])
        suffix = ""
        if entry.get("carried_forward"):
            suffix = colorize("  ⟲ prior scan", "dim")
        elif entry.get("placeholder"):
            suffix = colorize("  [unassessed]", "yellow")
        elif entry.get("stale"):
            suffix = colorize("  [stale — re-review]", "yellow")
        print(
            "  "
            + f"{entry['name']:<18} {bar} {entry['score']:5.1f}%  "
            + colorize(f"(strict {entry['strict']:5.1f}%)", "dim")
            + suffix
        )
    stale_keys = [e["dimension_key"] for e in entries if e.get("stale")]
    has_open = any(
        f.get("status") == "open" and not f.get("suppressed")
        for f in (state.get("findings") or {}).values()
    )
    if stale_keys and not has_open:
        n = len(stale_keys)
        dims_arg = ",".join(stale_keys)
        print(
            colorize(
                f"  {n} stale subjective dimension{'s' if n != 1 else ''}"
                f" — run `structorium review --run-batches --runner codex --parallel --scan-after-import --dimensions {dims_arg}` to re-review",
                "yellow",
            )
        )
    print()


def show_score_model_breakdown(state: dict, *, dim_scores: dict | None = None) -> None:
    """Show score recipe and weighted drags so users can see what drives the north star."""
    return presentation_mod.show_score_model_breakdown(
        state,
        scoring_mod=scoring_mod,
        colorize_fn=colorize,
        dim_scores=dim_scores,
    )


def show_dimension_deltas(prev: dict, current: dict):
    """Show which dimensions changed between scans (health and strict)."""
    return presentation_mod.show_dimension_deltas(
        prev,
        current,
        scoring_mod=scoring_mod,
        colorize_fn=colorize,
    )


def show_low_dimension_hints(dim_scores: dict):
    """Show actionable hints for dimensions below 50%."""
    return presentation_mod.show_low_dimension_hints(
        dim_scores,
        scoring_mod=scoring_mod,
        colorize_fn=colorize,
    )


def show_subjective_paths_section(
    state: dict,
    dim_scores: dict,
    *,
    threshold: float = 95.0,
) -> None:
    """Show explicit subjective-score improvement paths (coverage vs quality)."""
    return show_subjective_paths(
        state,
        dim_scores,
        colorize_fn=colorize,
        scorecard_subjective_entries_fn=scorecard_subjective_entries,
        threshold=threshold,
    )


__all__ = [
    "SubjectiveFollowup",
    "build_subjective_followup",
    "dimension_cli_key",
    "flatten_cli_keys",
    "scorecard_dimension_entries",
    "subjective_entries_for_dimension_keys",
    "subjective_integrity_followup",
    "subjective_integrity_notice_lines",
    "subjective_rerun_command",
    "show_detector_progress",
    "show_score_model_breakdown",
    "show_scorecard_subjective_measures",
    "show_dimension_deltas",
    "show_low_dimension_hints",
    "show_subjective_paths_section",
]
