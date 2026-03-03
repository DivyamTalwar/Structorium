"""Core batch processing helpers for holistic review workflows."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.commands.review.batch_prompt_template import render_batch_prompt
from app.commands.review.batch_scoring import DimensionMergeScorer
from intelligence.review.feedback_contract import (
    DIMENSION_NOTE_ISSUES_KEY,
    HIGH_SCORE_ISSUES_NOTE_THRESHOLD,
    LEGACY_DIMENSION_NOTE_ISSUES_KEY,
    LEGACY_REVIEW_QUALITY_HIGH_SCORE_MISSING_ISSUES_KEY,
    LOW_SCORE_FINDING_THRESHOLD,
    REVIEW_QUALITY_HIGH_SCORE_MISSING_ISSUES_KEY,
)
from intelligence.review.importing.contracts import (
    ReviewFindingPayload,
    validate_review_finding_payload,
)

_DIMENSION_SCORER = DimensionMergeScorer()
_EVIDENCE_PATH_PATTERN = re.compile(r"[A-Za-z0-9_./-]+\.[A-Za-z0-9_]+")


@dataclass(frozen=True)
class NormalizedBatchFinding:
    """Typed internal finding contract for normalized batch payloads."""

    dimension: str
    identifier: str
    summary: str
    confidence: str
    suggestion: str
    related_files: list[str]
    evidence: list[str]
    impact_scope: str
    fix_scope: str
    reasoning: str = ""
    evidence_lines: list[int] | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "dimension": self.dimension,
            "identifier": self.identifier,
            "summary": self.summary,
            "confidence": self.confidence,
            "suggestion": self.suggestion,
            "related_files": list(self.related_files),
            "evidence": list(self.evidence),
            "impact_scope": self.impact_scope,
            "fix_scope": self.fix_scope,
            "reasoning": self.reasoning,
        }
        if self.evidence_lines:
            payload["evidence_lines"] = list(self.evidence_lines)
        return payload


def parse_batch_selection(raw: str | None, batch_count: int) -> list[int]:
    """Parse optional 1-based CSV list of batches."""
    if not raw:
        return list(range(batch_count))

    selected: list[int] = []
    seen: set[int] = set()
    for token in raw.split(","):
        text = token.strip()
        if not text:
            continue
        idx_1 = int(text)
        if idx_1 < 1 or idx_1 > batch_count:
            raise ValueError(f"batch index {idx_1} out of range 1..{batch_count}")
        idx_0 = idx_1 - 1
        if idx_0 in seen:
            continue
        seen.add(idx_0)
        selected.append(idx_0)
    return selected


def extract_json_payload(raw: str, *, log_fn) -> dict[str, object] | None:
    """Best-effort extraction of first JSON object from agent output text."""
    text = raw.strip()
    if not text:
        return None

    decoder = json.JSONDecoder()
    last_decode_error: json.JSONDecodeError | None = None
    for start, ch in enumerate(text):
        if ch not in "{[":
            continue
        try:
            obj, _ = decoder.raw_decode(text[start:])
        except json.JSONDecodeError as exc:
            last_decode_error = exc
            continue
        if (
            isinstance(obj, dict)
            and isinstance(obj.get("assessments"), dict)
            and isinstance(obj.get("findings"), list)
        ):
            return obj
    if last_decode_error is not None:
        log_fn(f"  batch output JSON parse failed: {last_decode_error.msg}")
    else:
        log_fn("  batch output JSON parse failed: no valid payload found")
    return None


def _validate_dimension_note(
    key: str,
    note_raw: object,
) -> tuple[list[object], str, str, str, str]:
    """Validate a single dimension_notes entry and return parsed fields.

    Returns (evidence, impact_scope, fix_scope, confidence, issues_preventing_higher_score).
    Raises ValueError on invalid structure.
    """
    if not isinstance(note_raw, dict):
        raise ValueError(
            f"dimension_notes missing object for assessed dimension: {key}"
        )
    evidence = note_raw.get("evidence")
    impact_scope = note_raw.get("impact_scope")
    fix_scope = note_raw.get("fix_scope")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError(
            f"dimension_notes.{key}.evidence must be a non-empty array"
        )
    if not isinstance(impact_scope, str) or not impact_scope.strip():
        raise ValueError(
            f"dimension_notes.{key}.impact_scope must be a non-empty string"
        )
    if not isinstance(fix_scope, str) or not fix_scope.strip():
        raise ValueError(
            f"dimension_notes.{key}.fix_scope must be a non-empty string"
        )

    confidence_raw = str(note_raw.get("confidence", "medium")).strip().lower()
    confidence = (
        confidence_raw if confidence_raw in {"high", "medium", "low"} else "medium"
    )
    issues_note = str(note_raw.get(DIMENSION_NOTE_ISSUES_KEY, "")).strip()
    if not issues_note:
        issues_note = str(note_raw.get(LEGACY_DIMENSION_NOTE_ISSUES_KEY, "")).strip()
    return evidence, impact_scope, fix_scope, confidence, issues_note


def _normalize_abstraction_sub_axes(
    note_raw: dict[str, object],
    abstraction_sub_axes: tuple[str, ...],
) -> dict[str, float]:
    """Extract and clamp abstraction_fitness sub-axis scores from a note."""
    sub_axes_raw = note_raw.get("sub_axes")
    if sub_axes_raw is not None and not isinstance(sub_axes_raw, dict):
        raise ValueError(
            "dimension_notes.abstraction_fitness.sub_axes must be an object"
        )
    if not isinstance(sub_axes_raw, dict):
        return {}

    normalized: dict[str, float] = {}
    for axis in abstraction_sub_axes:
        axis_value = sub_axes_raw.get(axis)
        if axis_value is None:
            continue
        if isinstance(axis_value, bool) or not isinstance(
            axis_value, int | float
        ):
            raise ValueError(
                f"dimension_notes.abstraction_fitness.sub_axes.{axis} "
                "must be numeric"
            )
        normalized[axis] = round(
            max(0.0, min(100.0, float(axis_value))),
            1,
        )
    return normalized


def _normalize_findings(
    raw_findings: object,
    dimension_notes: dict[str, dict[str, Any]],
    *,
    max_batch_findings: int,
    allowed_dims: set[str],
    low_score_dimensions: set[str] | None = None,
) -> list[NormalizedBatchFinding]:
    """Validate and normalize the findings array from a batch payload."""
    if not isinstance(raw_findings, list):
        raise ValueError("findings must be an array")

    findings: list[NormalizedBatchFinding] = []
    errors: list[str] = []
    for idx, item in enumerate(raw_findings):
        finding: ReviewFindingPayload | None
        finding, finding_errors = validate_review_finding_payload(
            item,
            label=f"findings[{idx}]",
            allowed_dimensions=allowed_dims,
            allow_dismissed=False,
        )
        if finding_errors:
            errors.extend(finding_errors)
            continue
        assert finding is not None

        dim = finding["dimension"]
        note = dimension_notes.get(dim, {})
        impact_scope = str(
            (item if isinstance(item, dict) else {}).get(
                "impact_scope", note.get("impact_scope", "")
            )
        ).strip()
        fix_scope = str(
            (item if isinstance(item, dict) else {}).get(
                "fix_scope", note.get("fix_scope", "")
            )
        ).strip()
        if not impact_scope or not fix_scope:
            errors.append(
                f"findings[{idx}] requires impact_scope and fix_scope "
                "(or dimension_notes defaults)"
            )
            continue
        findings.append(
            NormalizedBatchFinding(
                dimension=finding["dimension"],
                identifier=finding["identifier"],
                summary=finding["summary"],
                confidence=finding["confidence"],
                suggestion=finding["suggestion"],
                related_files=list(finding.get("related_files", [])),
                evidence=list(finding.get("evidence", [])),
                impact_scope=impact_scope,
                fix_scope=fix_scope,
                reasoning=str(finding.get("reasoning", "")),
                evidence_lines=list(finding.get("evidence_lines", []))
                if isinstance(finding.get("evidence_lines"), list)
                else None,
            )
        )
    if errors:
        visible = errors[:10]
        remaining = len(errors) - len(visible)
        if remaining > 0:
            visible.append(f"... {remaining} additional finding schema error(s) omitted")
        raise ValueError("; ".join(visible))
    if len(findings) <= max_batch_findings:
        return findings

    required_dims = set(low_score_dimensions or set())
    if not required_dims:
        return findings[:max_batch_findings]

    # Preserve at least one finding per low-score dimension before trimming.
    selected: list[NormalizedBatchFinding] = []
    selected_indexes: set[int] = set()
    covered: set[str] = set()
    for idx, finding in enumerate(findings):
        if len(selected) >= max_batch_findings:
            break
        dim = finding.dimension.strip()
        if dim not in required_dims or dim in covered:
            continue
        selected.append(finding)
        selected_indexes.add(idx)
        covered.add(dim)

    for idx, finding in enumerate(findings):
        if len(selected) >= max_batch_findings:
            break
        if idx in selected_indexes:
            continue
        selected.append(finding)
    return selected


def _low_score_dimensions(assessments: dict[str, float]) -> set[str]:
    """Return assessed dimensions requiring explicit defect findings."""
    return {
        dim
        for dim, score in assessments.items()
        if score < LOW_SCORE_FINDING_THRESHOLD
    }


def _enforce_low_score_findings(
    *,
    assessments: dict[str, float],
    findings: list[NormalizedBatchFinding],
) -> None:
    """Fail closed when low scores do not report explicit findings."""
    required_dims = _low_score_dimensions(assessments)
    if not required_dims:
        return
    finding_dims = {
        finding.dimension.strip() for finding in findings
    }
    missing = sorted(dim for dim in required_dims if dim not in finding_dims)
    if not missing:
        return
    joined = ", ".join(missing)
    raise ValueError(
        "low-score dimensions must include at least one explicit finding: "
        f"{joined} (threshold {LOW_SCORE_FINDING_THRESHOLD:.1f})"
    )


def _normalize_confidence(value: object) -> str:
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"high", "medium", "low"}:
            return text
    return "medium"


def _extract_related_files_from_evidence(
    evidence: list[str],
    *,
    fallback: list[str],
    max_files: int = 3,
) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for entry in evidence:
        for token in _EVIDENCE_PATH_PATTERN.findall(entry):
            cleaned = token.strip("`'\".,:;()[]{}")
            if not cleaned or cleaned in {".", ".."}:
                continue
            if cleaned in seen:
                continue
            seen.add(cleaned)
            out.append(cleaned)
            if len(out) >= max_files:
                return out
    for candidate in fallback:
        cleaned = candidate.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
        if len(out) >= max_files:
            return out
    return out if out else ["."]


def _synthesize_low_score_finding(
    *,
    dimension: str,
    score: float,
    note: dict[str, Any],
    fallback_related_files: list[str],
) -> NormalizedBatchFinding | None:
    evidence_raw = note.get("evidence")
    evidence = [
        str(item).strip()
        for item in evidence_raw
        if isinstance(item, str) and str(item).strip()
    ] if isinstance(evidence_raw, list) else []
    if not evidence:
        return None

    issue_note = str(note.get(DIMENSION_NOTE_ISSUES_KEY, "")).strip()
    summary_base = (
        issue_note
        if issue_note
        else (
            "Low score indicates unresolved "
            f"{dimension.replace('_', ' ')} defects"
        )
    )
    summary = summary_base[:118].rstrip()
    identifier_seed = f"{dimension}|{score:.1f}|{summary}|{evidence[0]}"
    identifier_hash = hashlib.sha1(  # noqa: S324
        identifier_seed.encode("utf-8", errors="replace")
    ).hexdigest()[:10]
    related_files = _extract_related_files_from_evidence(
        evidence,
        fallback=fallback_related_files,
    )
    impact_scope = str(note.get("impact_scope", "module")).strip() or "module"
    fix_scope = str(note.get("fix_scope", "single_edit")).strip() or "single_edit"
    suggestion = (
        "Address the evidence-backed defects in this dimension and "
        "align implementation with the intended quality bar."
    )

    return NormalizedBatchFinding(
        dimension=dimension,
        identifier=f"auto_low_score_{identifier_hash}",
        summary=summary,
        confidence=_normalize_confidence(note.get("confidence")),
        suggestion=suggestion,
        related_files=related_files,
        evidence=evidence,
        impact_scope=impact_scope,
        fix_scope=fix_scope,
        reasoning=(
            "Synthesized finding to enforce low-score contract from dimension_notes "
            "when model output omitted a same-dimension defect entry."
        ),
    )


def _backfill_low_score_findings_from_notes(
    *,
    assessments: dict[str, float],
    findings: list[NormalizedBatchFinding],
    dimension_notes: dict[str, dict[str, Any]],
) -> list[NormalizedBatchFinding]:
    required_dims = _low_score_dimensions(assessments)
    if not required_dims:
        return findings

    finding_dims = {finding.dimension.strip() for finding in findings}
    missing_dims = sorted(dim for dim in required_dims if dim not in finding_dims)
    if not missing_dims:
        return findings

    fallback_related_files: list[str] = []
    seen_related: set[str] = set()
    for finding in findings:
        for path in finding.related_files:
            normalized = path.strip()
            if not normalized or normalized in seen_related:
                continue
            seen_related.add(normalized)
            fallback_related_files.append(normalized)

    backfilled = list(findings)
    for dimension in missing_dims:
        note = dimension_notes.get(dimension)
        if not isinstance(note, dict):
            continue
        synthesized = _synthesize_low_score_finding(
            dimension=dimension,
            score=float(assessments.get(dimension, 0.0)),
            note=note,
            fallback_related_files=fallback_related_files,
        )
        if synthesized is not None:
            backfilled.append(synthesized)
    return backfilled


def _compute_batch_quality(
    assessments: dict[str, float],
    findings: list[NormalizedBatchFinding],
    dimension_notes: dict[str, dict[str, Any]],
    allowed_dims: set[str],
    high_score_missing_issue_note: float,
) -> dict[str, float]:
    """Compute quality metrics for a single batch result."""
    return {
        "dimension_coverage": round(
            len(assessments) / max(len(allowed_dims), 1),
            3,
        ),
        "evidence_density": round(
            sum(len(note.get("evidence", [])) for note in dimension_notes.values())
            / max(len(findings), 1),
            3,
        ),
        REVIEW_QUALITY_HIGH_SCORE_MISSING_ISSUES_KEY: high_score_missing_issue_note,
    }


def normalize_batch_result(
    payload: dict[str, object],
    allowed_dims: set[str],
    *,
    max_batch_findings: int,
    abstraction_sub_axes: tuple[str, ...],
    allow_low_score_backfill: bool = False,
) -> tuple[
    dict[str, float],
    list[dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, float],
]:
    """Validate and normalize one batch payload."""
    if "assessments" not in payload:
        raise ValueError("payload missing required key: assessments")
    if "findings" not in payload:
        raise ValueError("payload missing required key: findings")

    raw_assessments = payload.get("assessments")
    if not isinstance(raw_assessments, dict):
        raise ValueError("assessments must be an object")

    raw_dimension_notes = payload.get("dimension_notes", {})
    if not isinstance(raw_dimension_notes, dict):
        raise ValueError("dimension_notes must be an object")

    assessments: dict[str, float] = {}
    dimension_notes: dict[str, dict[str, Any]] = {}
    high_score_missing_issue_note = 0.0
    for key, value in raw_assessments.items():
        if not isinstance(key, str) or not key:
            continue
        if key not in allowed_dims:
            continue
        if isinstance(value, bool):
            continue
        if not isinstance(value, int | float):
            continue
        score = round(max(0.0, min(100.0, float(value))), 1)

        note_raw = raw_dimension_notes.get(key)
        evidence, impact_scope, fix_scope, confidence, issues_note = (
            _validate_dimension_note(key, note_raw)
        )
        assert isinstance(note_raw, dict)
        if score > HIGH_SCORE_ISSUES_NOTE_THRESHOLD and not issues_note:
            high_score_missing_issue_note += 1

        normalized_sub_axes: dict[str, float] = {}
        if key == "abstraction_fitness" and isinstance(note_raw, dict):
            normalized_sub_axes = _normalize_abstraction_sub_axes(
                note_raw, abstraction_sub_axes
            )

        assessments[key] = score
        dimension_notes[key] = {
            "evidence": [str(item).strip() for item in evidence if str(item).strip()],
            "impact_scope": impact_scope.strip(),
            "fix_scope": fix_scope.strip(),
            "confidence": confidence,
            DIMENSION_NOTE_ISSUES_KEY: issues_note,
        }
        if normalized_sub_axes:
            dimension_notes[key]["sub_axes"] = normalized_sub_axes

    findings = _normalize_findings(
        payload.get("findings"),
        dimension_notes,
        max_batch_findings=max_batch_findings,
        allowed_dims=allowed_dims,
        low_score_dimensions=_low_score_dimensions(assessments),
    )
    if allow_low_score_backfill:
        findings = _backfill_low_score_findings_from_notes(
            assessments=assessments,
            findings=findings,
            dimension_notes=dimension_notes,
        )
    _enforce_low_score_findings(assessments=assessments, findings=findings)

    quality = _compute_batch_quality(
        assessments,
        findings,
        dimension_notes,
        allowed_dims,
        high_score_missing_issue_note,
    )
    return (
        assessments,
        [finding.to_payload() for finding in findings],
        dimension_notes,
        quality,
    )


def assessment_weight(
    *,
    dimension: str,
    findings: list[dict[str, Any]],
    dimension_notes: dict[str, dict[str, Any]],
) -> float:
    """Evidence-weighted assessment score weight with a neutral floor.

    Weighting is evidence-based and score-independent: the raw score does not
    influence how much weight a batch contributes during merge.
    """
    note = dimension_notes.get(dimension, {})
    note_evidence = len(note.get("evidence", [])) if isinstance(note, dict) else 0
    finding_count = sum(
        1
        for finding in findings
        if str(finding.get("dimension", "")).strip() == dimension
    )
    return float(1 + note_evidence + finding_count)


def _finding_pressure_by_dimension(
    findings: list[dict[str, Any]],
    *,
    dimension_notes: dict[str, dict[str, Any]],
) -> tuple[dict[str, float], dict[str, int]]:
    """Summarize how strongly findings should pull dimension scores down."""
    return _DIMENSION_SCORER.finding_pressure_by_dimension(
        findings,
        dimension_notes=dimension_notes,
    )


def _accumulate_batch_scores(
    result: dict[str, Any],
    *,
    score_buckets: dict[str, list[tuple[float, float]]],
    score_raw_by_dim: dict[str, list[float]],
    merged_dimension_notes: dict[str, dict[str, Any]],
    abstraction_axis_scores: dict[str, list[tuple[float, float]]],
    abstraction_sub_axes: tuple[str, ...],
) -> None:
    """Accumulate assessment scores, dimension notes, and sub-axis data from one batch."""
    result_findings = result.get("findings", [])
    result_notes = result.get("dimension_notes", {})
    for key, score in result.get("assessments", {}).items():
        if isinstance(score, bool):
            continue
        score_value = float(score)
        weight = assessment_weight(
            dimension=key,
            findings=result_findings,
            dimension_notes=result_notes,
        )
        score_buckets.setdefault(key, []).append((score_value, weight))
        score_raw_by_dim.setdefault(key, []).append(score_value)

        note = result_notes.get(key)
        existing = merged_dimension_notes.get(key)
        existing_evidence = (
            len(existing.get("evidence", [])) if isinstance(existing, dict) else -1
        )
        current_evidence = (
            len(note.get("evidence", [])) if isinstance(note, dict) else -1
        )
        if current_evidence > existing_evidence:
            merged_dimension_notes[key] = note

        if key == "abstraction_fitness" and isinstance(note, dict):
            sub_axes = note.get("sub_axes")
            if isinstance(sub_axes, dict):
                for axis in abstraction_sub_axes:
                    axis_score = sub_axes.get(axis)
                    if isinstance(axis_score, bool) or not isinstance(
                        axis_score, int | float
                    ):
                        continue
                    abstraction_axis_scores[axis].append(
                        (float(axis_score), weight)
                    )


def _normalize_word_set(text: str) -> set[str]:
    """Tokenize text into a normalized word set for light concept matching."""
    words = "".join(ch.lower() if ch.isalnum() else " " for ch in text).split()
    return {word for word in words if len(word) >= 3}


def _finding_identity_key(finding: dict[str, Any]) -> str:
    """Build a stable concept key; prefer dimension+identifier when available."""
    dim = str(finding.get("dimension", "")).strip()
    ident = str(finding.get("identifier", "")).strip()
    if ident:
        return f"{dim}::{ident}"
    summary = str(finding.get("summary", "")).strip()
    summary_terms = sorted(_normalize_word_set(summary))
    if summary_terms:
        return f"{dim}::summary::{','.join(summary_terms[:8])}"
    return f"{dim}::{summary}"


def _merge_finding_payload(existing: dict[str, Any], incoming: dict[str, Any]) -> None:
    """Merge two concept-equivalent findings into the existing payload."""
    for field in ("related_files", "evidence"):
        merged_values: list[str] = []
        seen: set[str] = set()
        for source in (existing.get(field), incoming.get(field)):
            if not isinstance(source, list):
                continue
            for item in source:
                text = str(item).strip()
                if not text or text in seen:
                    continue
                seen.add(text)
                merged_values.append(text)
        if merged_values:
            existing[field] = merged_values

    # Prefer richer summary/suggestion text when they differ.
    existing_summary = str(existing.get("summary", "")).strip()
    incoming_summary = str(incoming.get("summary", "")).strip()
    if len(incoming_summary) > len(existing_summary):
        existing["summary"] = incoming_summary

    existing_suggestion = str(existing.get("suggestion", "")).strip()
    incoming_suggestion = str(incoming.get("suggestion", "")).strip()
    if len(incoming_suggestion) > len(existing_suggestion):
        existing["suggestion"] = incoming_suggestion

    merged_from = existing.get("merged_from")
    if not isinstance(merged_from, list):
        merged_from = []
    incoming_identifier = str(incoming.get("identifier", "")).strip()
    if incoming_identifier and incoming_identifier not in merged_from:
        merged_from.append(incoming_identifier)
    if merged_from:
        existing["merged_from"] = merged_from


def _accumulate_batch_findings(
    result: dict[str, Any],
    finding_map: dict[str, dict[str, Any]],
) -> None:
    """Deduplicate and accumulate findings from one batch into finding_map."""
    for finding in result.get("findings", []):
        dedupe_key = _finding_identity_key(finding)
        existing = finding_map.get(dedupe_key)
        if existing is None:
            finding_map[dedupe_key] = finding
            continue
        _merge_finding_payload(existing, finding)


def _accumulate_batch_quality(
    result: dict[str, Any],
    *,
    coverage_values: list[float],
    evidence_density_values: list[float],
) -> float:
    """Accumulate quality metrics from one batch. Returns high-score-missing-issues delta."""
    quality = result.get("quality", {})
    if not isinstance(quality, dict):
        return 0.0
    coverage = quality.get("dimension_coverage")
    density = quality.get("evidence_density")
    missing_issue_note = quality.get(REVIEW_QUALITY_HIGH_SCORE_MISSING_ISSUES_KEY)
    if not isinstance(missing_issue_note, int | float):
        missing_issue_note = quality.get(
            LEGACY_REVIEW_QUALITY_HIGH_SCORE_MISSING_ISSUES_KEY
        )
    if isinstance(coverage, int | float):
        coverage_values.append(float(coverage))
    if isinstance(density, int | float):
        evidence_density_values.append(float(density))
    return (
        float(missing_issue_note)
        if isinstance(missing_issue_note, int | float)
        else 0.0
    )


def _compute_merged_assessments(
    score_buckets: dict[str, list[tuple[float, float]]],
    score_raw_by_dim: dict[str, list[float]],
    finding_pressure_by_dim: dict[str, float],
    finding_count_by_dim: dict[str, int],
) -> dict[str, float]:
    """Compute pressure-adjusted weighted mean for each dimension."""
    return _DIMENSION_SCORER.merge_scores(
        score_buckets,
        score_raw_by_dim,
        finding_pressure_by_dim,
        finding_count_by_dim,
    )


def _compute_abstraction_components(
    merged_assessments: dict[str, float],
    abstraction_axis_scores: dict[str, list[tuple[float, float]]],
    *,
    abstraction_sub_axes: tuple[str, ...],
    abstraction_component_names: dict[str, str],
) -> dict[str, float] | None:
    """Compute weighted abstraction sub-axis component scores.

    Returns component_scores dict, or None if abstraction_fitness is not assessed.
    """
    abstraction_score = merged_assessments.get("abstraction_fitness")
    if abstraction_score is None:
        return None

    component_scores: dict[str, float] = {}
    for axis in abstraction_sub_axes:
        weighted = abstraction_axis_scores.get(axis, [])
        if not weighted:
            continue
        numerator = sum(score * weight for score, weight in weighted)
        denominator = sum(weight for _, weight in weighted)
        if denominator <= 0:
            continue
        component_scores[abstraction_component_names[axis]] = round(
            max(0.0, min(100.0, numerator / denominator)),
            1,
        )
    return component_scores if component_scores else None


def merge_batch_results(
    batch_results: list[dict[str, Any]],
    *,
    abstraction_sub_axes: tuple[str, ...],
    abstraction_component_names: dict[str, str],
) -> dict[str, object]:
    """Deterministically merge assessments/findings across batch outputs."""
    score_buckets: dict[str, list[tuple[float, float]]] = {}
    score_raw_by_dim: dict[str, list[float]] = {}
    finding_map: dict[str, dict[str, Any]] = {}
    merged_dimension_notes: dict[str, dict[str, Any]] = {}
    coverage_values: list[float] = []
    evidence_density_values: list[float] = []
    high_score_missing_issue_note_total = 0.0
    abstraction_axis_scores: dict[str, list[tuple[float, float]]] = {
        axis: [] for axis in abstraction_sub_axes
    }

    for result in batch_results:
        _accumulate_batch_scores(
            result,
            score_buckets=score_buckets,
            score_raw_by_dim=score_raw_by_dim,
            merged_dimension_notes=merged_dimension_notes,
            abstraction_axis_scores=abstraction_axis_scores,
            abstraction_sub_axes=abstraction_sub_axes,
        )
        _accumulate_batch_findings(result, finding_map)
        high_score_missing_issue_note_total += _accumulate_batch_quality(
            result,
            coverage_values=coverage_values,
            evidence_density_values=evidence_density_values,
        )

    merged_findings = list(finding_map.values())
    finding_pressure_by_dim, finding_count_by_dim = _finding_pressure_by_dimension(
        merged_findings,
        dimension_notes=merged_dimension_notes,
    )

    merged_assessments = _compute_merged_assessments(
        score_buckets, score_raw_by_dim, finding_pressure_by_dim, finding_count_by_dim
    )

    merged_assessment_payload: dict[str, float | dict[str, object]] = {
        key: value for key, value in merged_assessments.items()
    }
    component_scores = _compute_abstraction_components(
        merged_assessments,
        abstraction_axis_scores,
        abstraction_sub_axes=abstraction_sub_axes,
        abstraction_component_names=abstraction_component_names,
    )
    if component_scores is not None:
        merged_assessment_payload["abstraction_fitness"] = {
            "score": merged_assessments["abstraction_fitness"],
            "components": list(component_scores),
            "component_scores": component_scores,
        }

    return {
        "assessments": merged_assessment_payload,
        "dimension_notes": merged_dimension_notes,
        "findings": merged_findings,
        "review_quality": {
            "batch_count": len(batch_results),
            "dimension_coverage": round(
                sum(coverage_values) / max(len(coverage_values), 1),
                3,
            ),
            "evidence_density": round(
                sum(evidence_density_values) / max(len(evidence_density_values), 1),
                3,
            ),
            REVIEW_QUALITY_HIGH_SCORE_MISSING_ISSUES_KEY: int(
                high_score_missing_issue_note_total
            ),
            "finding_pressure": round(sum(finding_pressure_by_dim.values()), 3),
            "dimensions_with_findings": len(finding_count_by_dim),
        },
    }


def build_batch_prompt(
    *,
    repo_root: Path,
    packet_path: Path,
    batch_index: int,
    batch: dict[str, object],
) -> str:
    """Render one subagent prompt for a holistic investigation batch."""
    return render_batch_prompt(
        repo_root=repo_root,
        packet_path=packet_path,
        batch_index=batch_index,
        batch=batch,
    )


__all__ = [
    "assessment_weight",
    "build_batch_prompt",
    "extract_json_payload",
    "merge_batch_results",
    "normalize_batch_result",
    "parse_batch_selection",
]
