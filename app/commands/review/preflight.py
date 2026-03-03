"""Preflight guards for subjective review reruns.

Blocks --prepare / --run-batches / --external-start when the objective plan
still has open items, unless --force-review-rerun is set.  Also auto-clears
stale subjective markers before a new review cycle.
"""

from __future__ import annotations

import sys

from core.output_api import colorize
from engine._work_queue.core import QueueBuildOptions, build_work_queue
from state import StateModel, save_state

from .helpers import parse_dimensions


def clear_stale_subjective_entries(
    state: StateModel,
    *,
    dimensions: set[str] | None = None,
) -> list[str]:
    """Clear ``needs_review_refresh`` markers from subjective assessments.

    When *dimensions* is provided, only those dimensions are cleared;
    otherwise all stale dimensions are cleared.

    Returns the list of dimension keys that were cleared.
    """
    assessments: dict = state.get("subjective_assessments", {})
    cleared: list[str] = []
    for dim_key, assessment in assessments.items():
        if not isinstance(assessment, dict):
            continue
        if dimensions is not None and dim_key not in dimensions:
            continue
        if assessment.get("needs_review_refresh"):
            assessment.pop("needs_review_refresh", None)
            assessment.pop("stale_since", None)
            assessment.pop("refresh_reason", None)
            cleared.append(dim_key)
    return cleared


def _scored_dimensions(state: StateModel) -> list[str]:
    """Return dimension keys that already have a nonzero subjective score."""
    assessments: dict = state.get("subjective_assessments", {})
    scored: list[str] = []
    for dim_key, assessment in assessments.items():
        if isinstance(assessment, dict):
            if assessment.get("score", 0):
                scored.append(dim_key)
        elif isinstance(assessment, (int, float)) and assessment:
            scored.append(dim_key)
    return sorted(scored)


def review_rerun_preflight(
    state: StateModel,
    args,
    *,
    state_file=None,
    save_fn=save_state,
) -> None:
    """Single entry point: gate check -> clear stale -> save.

    Exits with code 1 when open objective items exist and
    ``--force-review-rerun`` is not set.  On success, clears stale
    subjective markers for the targeted dimensions and persists state.
    """
    dimensions = parse_dimensions(args)

    # --force-review-rerun bypasses the gate
    if getattr(args, "force_review_rerun", False):
        print(
            colorize(
                "  --force-review-rerun: bypassing objective-plan-drained check.",
                "yellow",
            )
        )
    else:
        # Only gate dimensions that are actually targeted by this review run.
        scored_dims = _scored_dimensions(state)
        if dimensions is not None:
            blocking_dims = sorted(d for d in scored_dims if d in dimensions)
        else:
            blocking_dims = scored_dims

        # No gate when none of the targeted dimensions have prior scores —
        # this is a first run for these dimensions, not a rerun.
        if blocking_dims:
            result = build_work_queue(
                state,
                options=QueueBuildOptions(
                    status="open",
                    include_subjective=False,
                    count=None,
                ),
            )
            total = result["total"]
            if total > 0:
                print(
                    colorize(
                        f"  Blocked: {total} open objective finding(s) — this is a review rerun.",
                        "red",
                    ),
                    file=sys.stderr,
                )
                print(
                    colorize(
                        f"  Scored dimensions: {', '.join(blocking_dims)}",
                        "yellow",
                    ),
                    file=sys.stderr,
                )
                print("", file=sys.stderr)
                if dimensions is not None:
                    unscored = sorted(dimensions - set(blocking_dims))
                    if unscored:
                        print(
                            colorize(
                                f"  Tip: target only unscored dimensions with "
                                f"--dimensions {','.join(unscored)}",
                                "dim",
                            ),
                            file=sys.stderr,
                        )
                print(
                    colorize(
                        "  Resolve open items first, or override with --force-review-rerun",
                        "dim",
                    ),
                    file=sys.stderr,
                )
                sys.exit(1)

    # Gate passed — clear stale for targeted dims
    cleared = clear_stale_subjective_entries(state, dimensions=dimensions)
    if cleared and state_file:
        save_fn(state, state_file)
        print(
            colorize(
                f"  Cleared stale review markers: {', '.join(sorted(cleared))}",
                "cyan",
            )
        )
