"""Review preparation flow for `structorium fix review`."""

from __future__ import annotations

import sys
from pathlib import Path

import state as state_mod
from app.commands.helpers.lang import resolve_lang
from app.commands.helpers.query import write_query
from app.commands.helpers.runtime import command_runtime
from app.commands.helpers.state import state_path
from app.commands.review import runtime as review_runtime_mod
from core.fallbacks import print_error
from intelligence import integrity as subjective_integrity_mod
from intelligence import review as review_mod
from core.output_api import colorize


def _cmd_fix_review(args):
    """Prepare structured review data with dimension templates for AI evaluation."""
    runtime = command_runtime(args)
    lang_cfg = resolve_lang(args)
    if not lang_cfg:
        print_error("could not detect language. Use --lang.")
        sys.exit(1)

    state = state_mod.load_state(state_path(args))
    path = Path(args.path)

    lang_run, found_files = review_runtime_mod.setup_lang_concrete(
        lang_cfg,
        path,
        runtime.config,
    )
    data = review_mod.prepare_review(
        path,
        lang_run,
        state,
        options=review_mod.ReviewPrepareOptions(files=found_files or None),
    )

    if data["total_candidates"] == 0:
        print(
            colorize(
                "\n  All production files have been reviewed. Nothing to do.", "green"
            )
        )
        unassessed_dims = subjective_integrity_mod.unassessed_subjective_dimensions(
            state.get("dimension_scores", {})
        )
        scoped_findings = state_mod.path_scoped_findings(
            state.get("findings", {}),
            state.get("scan_path"),
        )
        _coverage_total, _reasons, holistic_reasons = (
            subjective_integrity_mod.subjective_review_open_breakdown(scoped_findings)
        )
        holistic_open = sum(holistic_reasons.values())
        if unassessed_dims or holistic_open > 0:
            print(colorize("  Subjective integrity still needs refresh.", "yellow"))
            if unassessed_dims:
                rendered = ", ".join(unassessed_dims[:3])
                if len(unassessed_dims) > 3:
                    rendered = f"{rendered}, +{len(unassessed_dims) - 3} more"
                print(colorize(f"    Unassessed (0% placeholder): {rendered}", "dim"))
            if holistic_open > 0:
                print(
                    colorize(
                        f"    Holistic stale/missing signals: {holistic_open}", "dim"
                    )
                )
            print(
                colorize(
                    "    Preferred: `structorium review --run-batches --runner codex --parallel --scan-after-import`",
                    "dim",
                )
            )
            print(
                colorize(
                    "    Claude cloud durable path: `structorium review --external-start --external-runner claude`, then run the printed `--external-submit ... --scan-after-import` command",
                    "dim",
                )
            )
            print(
                colorize(
                    "    Findings-only fallback: `structorium review --prepare`, then `structorium review --import findings.json && structorium scan`",
                    "dim",
                )
            )
        return

    print(
        colorize(f"\n  {data['total_candidates']} files need design review\n", "bold")
    )

    dims = data.get("dimensions", [])
    prompts = data.get("dimension_prompts", {})
    for dim in dims:
        prompt = prompts.get(dim)
        if not prompt:
            continue
        print(colorize(f"  {dim}", "cyan"))
        print(colorize(f"    {prompt['description']}", "dim"))
        print(colorize("    Look for:", "dim"))
        for item in prompt.get("look_for", []):
            print(colorize(f"      - {item}", "dim"))
        skip = prompt.get("skip", [])
        if skip:
            print(colorize("    Skip:", "dim"))
            for item in skip:
                print(colorize(f"      - {item}", "dim"))
        print()

    lang_guide = data.get("lang_guidance") or review_mod.get_lang_guidance(
        lang_run.name
    )
    if lang_guide:
        print(colorize(f"  Language: {lang_run.name}", "cyan"))
        if lang_guide.get("naming"):
            print(colorize(f"    Naming: {lang_guide['naming']}", "dim"))
        for pattern in lang_guide.get("patterns", []):
            print(colorize(f"    - {pattern}", "dim"))
        print()

    write_query(data)
    print(colorize("  Review data written to .structorium/query.json", "dim"))
    print(colorize("\n  AGENT PLAN (run in order):", "yellow"))
    print(
        colorize(
            "  1. Read query.json — it includes file content, context, and prompts",
            "dim",
        )
    )
    print(colorize("  2. Evaluate each file against the dimensions above", "dim"))
    print(colorize("  3. Save findings as JSON (for example: findings.json)", "dim"))
    print(
        colorize(
            "  4. Preferred (Codex local): structorium review --run-batches --runner codex --parallel --scan-after-import",
            "dim",
        )
    )
    print(
        colorize(
            "  5. Claude cloud durable path: structorium review --external-start --external-runner claude (then run the printed --external-submit ... --scan-after-import command)",
            "dim",
        )
    )
    print(
        colorize(
            "  6. Findings-only fallback: structorium review --import findings.json && structorium scan",
            "dim",
        )
    )
    print(
        colorize(
            "  Next command to improve subjective scores: `structorium review --run-batches --runner codex --parallel --scan-after-import`",
            "dim",
        )
    )
    print()
