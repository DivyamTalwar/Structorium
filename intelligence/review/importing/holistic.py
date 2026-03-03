"""Holistic review finding import workflow."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from intelligence.review.dimensions import normalize_dimension_name
from intelligence.review.dimensions.data import load_dimensions_for_lang
from intelligence.review.importing.contracts import (
    ReviewFindingPayload,
    ReviewImportPayload,
    ReviewScopePayload,
    validate_review_finding_payload,
)
from intelligence.review.importing.shared import (
    _lang_potentials,
    auto_resolve_review_findings,
    normalize_review_confidence,
    parse_review_import_payload,
    refresh_review_file_cache,
    review_tier,
    ReviewImportEnvelope,
    store_assessments,
)
from intelligence.review.selection import hash_file
from scoring import HOLISTIC_POTENTIAL
from state import MergeScanOptions, make_finding, merge_scan, utc_now

# Backward-compatible test patch hook (runtime root now resolves lazily).
PROJECT_ROOT: Path | None = None


def parse_holistic_import_payload(
    data: ReviewImportPayload | dict[str, Any],
) -> tuple[list[ReviewFindingPayload], dict[str, Any] | None, list[str]]:
    """Parse strict holistic import payload object."""
    payload = parse_review_import_payload(data, mode_name="Holistic")
    return payload.findings, payload.assessments, payload.reviewed_files


def update_reviewed_file_cache(
    state: dict[str, Any],
    reviewed_files: list[str],
    *,
    project_root: Path | str | None = None,
    utc_now_fn=utc_now,
) -> None:
    """Refresh per-file review cache entries from holistic payload metadata."""
    refresh_review_file_cache(
        state,
        reviewed_files=reviewed_files,
        findings_by_file=None,
        project_root=project_root,
        hash_file_fn=hash_file,
        utc_now_fn=utc_now_fn,
    )


_POSITIVE_PREFIXES = (
    "good ",
    "well ",
    "strong ",
    "clean ",
    "excellent ",
    "nice ",
    "solid ",
)


def _validate_and_build_findings(
    findings_list: list[ReviewFindingPayload],
    holistic_prompts: dict[str, Any],
    lang_name: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate raw holistic findings and build state-ready finding dicts.

    Returns (review_findings, skipped, dismissed_concerns).
    """
    review_findings: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    dismissed_concerns: list[dict[str, Any]] = []
    allowed_dimensions = {
        dim for dim in holistic_prompts if isinstance(dim, str) and dim.strip()
    }

    for idx, raw_finding in enumerate(findings_list):
        finding, finding_errors = validate_review_finding_payload(
            raw_finding,
            label=f"findings[{idx}]",
            allowed_dimensions=allowed_dimensions,
            allow_dismissed=True,
        )
        if finding_errors:
            skipped.append(
                {
                    "index": idx,
                    "missing": finding_errors,
                    "identifier": (
                        raw_finding.get("identifier", "<none>")
                        if isinstance(raw_finding, dict)
                        else "<none>"
                    ),
                }
            )
            continue
        assert finding is not None

        # Handle dismissed concern verdicts (no dimension/summary required).
        if finding.get("concern_verdict") == "dismissed":
            fp = finding.get("concern_fingerprint", "")
            if fp:
                dismissed_concerns.append(
                    {
                        "fingerprint": fp,
                        "concern_type": finding.get("concern_type", ""),
                        "concern_file": finding.get("concern_file", ""),
                        "reasoning": finding.get("reasoning", ""),
                    }
                )
            continue

        # Safety net: skip positive observations that slipped past the prompt.
        summary_text = str(finding.get("summary", ""))
        if summary_text.lower().startswith(_POSITIVE_PREFIXES):
            skipped.append(
                {
                    "index": idx,
                    "missing": ["positive observation (not a defect)"],
                    "identifier": finding.get("identifier", "<none>"),
                }
            )
            continue

        dimension = finding["dimension"]

        # Confirmed concern verdicts become "concerns" detector findings.
        is_confirmed_concern = finding.get("concern_verdict") == "confirmed"
        detector = "concerns" if is_confirmed_concern else "review"

        content_hash = hashlib.sha256(summary_text.encode()).hexdigest()[:8]
        detail: dict[str, Any] = {
            "holistic": True,
            "dimension": dimension,
            "related_files": finding["related_files"],
            "evidence": finding["evidence"],
            "suggestion": finding.get("suggestion", ""),
            "reasoning": finding.get("reasoning", ""),
        }
        if is_confirmed_concern:
            detail["concern_type"] = finding.get("concern_type", "")
            detail["concern_verdict"] = "confirmed"

        prefix = "concern" if is_confirmed_concern else "holistic"
        file = finding.get("concern_file", "") if is_confirmed_concern else ""
        confidence = normalize_review_confidence(finding.get("confidence", "low"))
        imported = make_finding(
            detector=detector,
            file=file,
            name=f"{prefix}::{dimension}::{finding['identifier']}::{content_hash}",
            tier=review_tier(confidence, holistic=True),
            confidence=confidence,
            summary=summary_text,
            detail=detail,
        )
        imported["lang"] = lang_name
        review_findings.append(imported)

    return review_findings, skipped, dismissed_concerns


def _collect_imported_dimensions(
    *,
    findings_list: list[ReviewFindingPayload],
    review_findings: list[dict[str, Any]],
    assessments: dict[str, Any] | None,
    review_scope: ReviewScopePayload | dict[str, Any] | None,
    valid_dimensions: set[str],
) -> set[str]:
    """Return normalized dimensions this import explicitly covered."""
    imported_dimensions: set[str] = set()

    if isinstance(review_scope, dict):
        scope_dims = review_scope.get("imported_dimensions")
        if isinstance(scope_dims, list):
            for raw_dim in scope_dims:
                normalized = normalize_dimension_name(str(raw_dim))
                if normalized in valid_dimensions:
                    imported_dimensions.add(normalized)

    for finding in findings_list:
        if not isinstance(finding, dict):
            continue
        normalized = normalize_dimension_name(str(finding.get("dimension", "")))
        if normalized in valid_dimensions:
            imported_dimensions.add(normalized)

    for finding in review_findings:
        detail = finding.get("detail")
        if not isinstance(detail, dict):
            continue
        normalized = normalize_dimension_name(str(detail.get("dimension", "")))
        if normalized in valid_dimensions:
            imported_dimensions.add(normalized)

    for raw_dim in (assessments or {}):
        normalized = normalize_dimension_name(str(raw_dim))
        if normalized in valid_dimensions:
            imported_dimensions.add(normalized)

    return imported_dimensions


def _auto_resolve_stale_holistic(
    state: dict[str, Any],
    new_ids: set[str],
    diff: dict[str, Any],
    utc_now_fn,
    *,
    imported_dimensions: set[str] | None = None,
    full_sweep_included: bool | None = None,
) -> None:
    """Auto-resolve open holistic findings not present in the latest import."""
    scope_dimensions = {
        normalize_dimension_name(dim)
        for dim in (imported_dimensions or set())
        if isinstance(dim, str) and dim.strip()
    }
    scoped_reimport = full_sweep_included is False
    # Partial re-import with unknown dimension scope: do not auto-resolve.
    if scoped_reimport and not scope_dimensions:
        return

    def _should_resolve(finding: dict[str, Any]) -> bool:
        if finding.get("detector") not in ("review", "concerns"):
            return False
        detail = finding.get("detail")
        if not isinstance(detail, dict) or not detail.get("holistic"):
            return False
        if not scoped_reimport:
            return True
        dimension = normalize_dimension_name(str(detail.get("dimension", "")))
        return dimension in scope_dimensions

    auto_resolve_review_findings(
        state,
        new_ids=new_ids,
        diff=diff,
        note="not reported in latest holistic re-import",
        should_resolve=_should_resolve,
        utc_now_fn=utc_now_fn,
    )


def import_holistic_findings(
    findings_data: ReviewImportPayload,
    state: dict[str, Any],
    lang_name: str,
    *,
    project_root: Path | str | None = None,
    utc_now_fn=utc_now,
) -> dict[str, Any]:
    """Import holistic (codebase-wide) findings into state."""
    payload: ReviewImportEnvelope = parse_review_import_payload(
        findings_data,
        mode_name="Holistic",
    )
    findings_list = payload.findings
    assessments = payload.assessments
    reviewed_files = payload.reviewed_files
    review_scope = findings_data.get("review_scope", {})
    if not isinstance(review_scope, dict):
        review_scope = {}
    scope_full_sweep = review_scope.get("full_sweep_included")
    if not isinstance(scope_full_sweep, bool):
        scope_full_sweep = None
    if assessments:
        store_assessments(
            state,
            assessments,
            source="holistic",
            utc_now_fn=utc_now_fn,
        )

    _, holistic_prompts, _ = load_dimensions_for_lang(lang_name)
    valid_dimensions = {
        normalize_dimension_name(dim)
        for dim in holistic_prompts
        if isinstance(dim, str)
    }
    review_findings, skipped, dismissed_concerns = _validate_and_build_findings(
        findings_list, holistic_prompts, lang_name
    )
    imported_dimensions = _collect_imported_dimensions(
        findings_list=findings_list,
        review_findings=review_findings,
        assessments=assessments if isinstance(assessments, dict) else None,
        review_scope=review_scope,
        valid_dimensions=valid_dimensions,
    )

    # Store dismissed concern verdicts for suppression in future concern generation.
    if dismissed_concerns:
        from engine.concerns import generate_concerns

        store = state.setdefault("concern_dismissals", {})
        now = utc_now_fn()
        # Compute current concerns to get source_finding_ids for each fingerprint.
        current_concerns = generate_concerns(state, lang_name=lang_name)
        concern_sources = {
            c.fingerprint: list(c.source_findings) for c in current_concerns
        }
        for dc in dismissed_concerns:
            fp = dc["fingerprint"]
            store[fp] = {
                "dismissed_at": now,
                "reasoning": dc.get("reasoning", ""),
                "concern_type": dc.get("concern_type", ""),
                "concern_file": dc.get("concern_file", ""),
                "source_finding_ids": concern_sources.get(fp, []),
            }

    potentials = _lang_potentials(state, lang_name)
    existing_review = potentials.get("review", 0)
    potentials["review"] = max(existing_review, HOLISTIC_POTENTIAL)

    concern_count = sum(1 for f in review_findings if f.get("detector") == "concerns")
    if concern_count:
        potentials["concerns"] = max(potentials.get("concerns", 0), concern_count)

    merge_potentials_dict: dict[str, int] = {"review": potentials.get("review", 0)}
    if potentials.get("concerns", 0) > 0:
        merge_potentials_dict["concerns"] = potentials["concerns"]

    diff = merge_scan(
        state,
        review_findings,
        options=MergeScanOptions(
            lang=lang_name,
            potentials=merge_potentials_dict,
            merge_potentials=True,
        ),
    )

    new_ids = {finding["id"] for finding in review_findings}
    _auto_resolve_stale_holistic(
        state,
        new_ids,
        diff,
        utc_now_fn,
        imported_dimensions=imported_dimensions,
        full_sweep_included=scope_full_sweep,
    )

    if skipped:
        diff["skipped"] = len(skipped)
        diff["skipped_details"] = skipped

    update_reviewed_file_cache(
        state,
        reviewed_files,
        project_root=project_root,
        utc_now_fn=utc_now_fn,
    )
    resolve_reviewed_file_coverage_findings(
        state,
        diff,
        reviewed_files,
        utc_now_fn=utc_now_fn,
    )
    update_holistic_review_cache(
        state,
        findings_list,
        lang_name=lang_name,
        review_scope=review_scope,
        utc_now_fn=utc_now_fn,
    )
    resolve_holistic_coverage_findings(state, diff, utc_now_fn=utc_now_fn)

    # Clean up dismissals whose source findings were all resolved — runs after
    # all finding mutations (merge_scan, auto_resolve, coverage resolve) so it
    # sees the final state.
    from engine.concerns import cleanup_stale_dismissals

    cleanup_stale_dismissals(state)

    return diff


def _resolve_total_files(state: dict[str, Any], lang_name: str | None) -> int:
    """Best-effort total file count from codebase_metrics or review cache."""
    review_cache = state.get("review_cache", {})
    fallback = len(review_cache.get("files", {}))

    codebase_metrics = state.get("codebase_metrics", {})
    if not isinstance(codebase_metrics, dict):
        return fallback

    # Try language-specific metrics first, then global.
    sources = []
    if lang_name:
        lang_metrics = codebase_metrics.get(lang_name)
        if isinstance(lang_metrics, dict):
            sources.append(lang_metrics)
    sources.append(codebase_metrics)

    for source in sources:
        metric_total = source.get("total_files")
        if isinstance(metric_total, int) and metric_total > 0:
            return metric_total

    return fallback


def update_holistic_review_cache(
    state: dict[str, Any],
    findings_data: list[dict],
    *,
    lang_name: str | None = None,
    review_scope: dict[str, Any] | None = None,
    utc_now_fn=utc_now,
) -> None:
    """Store holistic review metadata in review_cache."""
    review_cache = state.setdefault("review_cache", {})
    now = utc_now_fn()
    _, holistic_prompts, _ = load_dimensions_for_lang(lang_name or "")

    valid = [
        finding
        for finding in findings_data
        if all(
            key in finding
            for key in ("dimension", "identifier", "summary", "confidence")
        )
        and finding["dimension"] in holistic_prompts
    ]

    resolved_total_files: int
    total_override = (
        review_scope.get("total_files")
        if isinstance(review_scope, dict)
        else None
    )
    if (
        isinstance(total_override, int)
        and not isinstance(total_override, bool)
        and total_override > 0
    ):
        resolved_total_files = total_override
    else:
        resolved_total_files = _resolve_total_files(state, lang_name)

    holistic_entry: dict[str, Any] = {
        "reviewed_at": now,
        "file_count_at_review": resolved_total_files,
        "finding_count": len(valid),
    }
    if isinstance(review_scope, dict):
        reviewed_files_count = review_scope.get("reviewed_files_count")
        if (
            isinstance(reviewed_files_count, int)
            and not isinstance(reviewed_files_count, bool)
            and reviewed_files_count >= 0
        ):
            holistic_entry["reviewed_files_count"] = reviewed_files_count
        full_sweep_included = review_scope.get("full_sweep_included")
        if isinstance(full_sweep_included, bool):
            holistic_entry["full_sweep_included"] = full_sweep_included

    review_cache["holistic"] = holistic_entry


def resolve_holistic_coverage_findings(
    state: dict[str, Any],
    diff: dict[str, Any],
    *,
    utc_now_fn=utc_now,
) -> None:
    """Resolve stale holistic coverage entries after successful holistic import."""
    now = utc_now_fn()
    for finding in state.get("findings", {}).values():
        if finding.get("status") != "open":
            continue
        if finding.get("detector") != "subjective_review":
            continue

        finding_id = finding.get("id", "")
        if (
            "::holistic_unreviewed" not in finding_id
            and "::holistic_stale" not in finding_id
        ):
            continue

        finding["status"] = "auto_resolved"
        finding["resolved_at"] = now
        finding["note"] = "resolved by holistic review import"
        finding["resolution_attestation"] = {
            "kind": "agent_import",
            "text": "Holistic review refreshed; coverage marker superseded",
            "attested_at": now,
            "scan_verified": False,
        }
        diff["auto_resolved"] += 1


def resolve_reviewed_file_coverage_findings(
    state: dict[str, Any],
    diff: dict[str, Any],
    reviewed_files: list[str],
    *,
    utc_now_fn=utc_now,
) -> None:
    """Resolve per-file subjective coverage markers for freshly reviewed files."""
    if not reviewed_files:
        return

    reviewed_set = {path for path in reviewed_files if isinstance(path, str) and path}
    if not reviewed_set:
        return

    now = utc_now_fn()
    for finding in state.get("findings", {}).values():
        if finding.get("status") != "open":
            continue
        if finding.get("detector") != "subjective_review":
            continue

        finding_id = finding.get("id", "")
        if "::holistic_unreviewed" in finding_id or "::holistic_stale" in finding_id:
            continue

        finding_file = finding.get("file", "")
        if finding_file not in reviewed_set:
            continue

        finding["status"] = "auto_resolved"
        finding["resolved_at"] = now
        finding["note"] = "resolved by reviewed_files cache refresh"
        finding["resolution_attestation"] = {
            "kind": "agent_import",
            "text": "Per-file review cache refreshed for this file",
            "attested_at": now,
            "scan_verified": False,
        }
        diff["auto_resolved"] += 1
