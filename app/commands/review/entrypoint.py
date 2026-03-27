"""CLI entrypoint for review command."""

from __future__ import annotations

import argparse
import sys

from app.commands.helpers.lang import resolve_lang
from app.commands.helpers.runtime import command_runtime
from core.output_api import colorize

from .batch import _do_run_batches
from .external import do_external_start, do_external_submit
from .import_cmd import do_import, do_validate_import
from .preflight import review_rerun_preflight
from .prepare import do_prepare


class ReviewValidationError(ValueError):
    """Raised when review command flag validation fails.

    Caught by the top-level CLI handler to produce a clean error message
    without a traceback. This replaces scattered sys.exit() calls to
    keep exit handling consistent and the function testable.
    """


def _enable_live_review_output() -> None:
    """Best-effort: force line-buffered review output for non-TTY runners."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(line_buffering=True, write_through=True)
        except (OSError, ValueError, TypeError):
            continue


def _validate_review_flags(args) -> None:
    """Validate mutually-exclusive review mode flags up front.

    Raises ReviewValidationError on invalid flag combinations so that
    all validation happens before any work is done.
    """
    merge = bool(getattr(args, "merge", False))
    run_batches = bool(getattr(args, "run_batches", False))
    external_start = bool(getattr(args, "external_start", False))
    external_submit = bool(getattr(args, "external_submit", False))
    import_file = getattr(args, "import_file", None)
    validate_import_file = getattr(args, "validate_import_file", None)

    import_mode = bool(import_file) and not external_submit
    mode_flags = [
        merge,
        run_batches,
        external_start,
        external_submit,
        import_mode,
        bool(validate_import_file),
    ]
    if sum(1 for enabled in mode_flags if enabled) > 1:
        raise ReviewValidationError(
            "choose one review mode per command "
            "(--merge | --run-batches | --external-start | --external-submit | --import | --validate-import)."
        )

    if external_submit and not import_file:
        raise ReviewValidationError(
            "--external-submit requires --import FILE."
        )

    if external_submit and not getattr(args, "session_id", None):
        raise ReviewValidationError(
            "--external-submit requires --session-id."
        )


def cmd_review(args: argparse.Namespace) -> None:
    """Prepare or import subjective code review findings."""
    _enable_live_review_output()
    runtime = command_runtime(args)
    state_file = runtime.state_path
    state = runtime.state
    lang = resolve_lang(args)

    if not lang:
        raise ReviewValidationError(
            "could not detect language. Use --lang."
        )

    # Validate all flags before doing any work.
    _validate_review_flags(args)

    merge = bool(getattr(args, "merge", False))
    run_batches = bool(getattr(args, "run_batches", False))
    external_start = bool(getattr(args, "external_start", False))
    external_submit = bool(getattr(args, "external_submit", False))
    import_file = getattr(args, "import_file", None)
    validate_import_file = getattr(args, "validate_import_file", None)

    if merge:
        from app.commands.review.merge import do_merge

        do_merge(args)
        return

    if run_batches:
        review_rerun_preflight(state, args, state_file=state_file)
        _do_run_batches(
            args,
            state,
            lang,
            state_file,
            config=runtime.config,
        )
        return

    if external_start:
        review_rerun_preflight(state, args, state_file=state_file)
        do_external_start(
            args,
            state,
            lang,
            config=runtime.config,
        )
        return

    if external_submit:
        do_external_submit(
            import_file=str(import_file),
            session_id=str(getattr(args, "session_id")),
            state=state,
            lang=lang,
            state_file=state_file,
            config=runtime.config,
            allow_partial=bool(getattr(args, "allow_partial", False)),
            scan_after_import=bool(getattr(args, "scan_after_import", False)),
            scan_path=str(getattr(args, "path", ".") or "."),
            dry_run=bool(getattr(args, "dry_run", False)),
        )
        return

    if validate_import_file:
        do_validate_import(
            validate_import_file,
            lang,
            allow_partial=bool(getattr(args, "allow_partial", False)),
            manual_override=bool(getattr(args, "manual_override", False)),
            attested_external=bool(getattr(args, "attested_external", False)),
            manual_attest=getattr(args, "attest", None),
        )
        return

    if import_file:
        do_import(
            import_file,
            state,
            lang,
            state_file,
            config=runtime.config,
            allow_partial=bool(getattr(args, "allow_partial", False)),
            manual_override=bool(getattr(args, "manual_override", False)),
            attested_external=bool(getattr(args, "attested_external", False)),
            manual_attest=getattr(args, "attest", None),
        )
    else:
        review_rerun_preflight(state, args, state_file=state_file)
        do_prepare(args, state, lang, state_file, config=runtime.config)
