"""Scoring primitives for holistic review batch merges."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_CONFIDENCE_WEIGHTS = {
    "high": 1.2,
    "medium": 1.0,
    "low": 0.75,
}
_IMPACT_SCOPE_WEIGHTS = {
    "local": 1.0,
    "module": 1.3,
    "subsystem": 1.6,
    "codebase": 2.0,
}
_FIX_SCOPE_WEIGHTS = {
    "single_edit": 1.0,
    "multi_file_refactor": 1.3,
    "architectural_change": 1.7,
}

# Blending ratio between weighted mean and per-batch floor score.
_WEIGHTED_MEAN_BLEND = 0.7
_FLOOR_BLEND_WEIGHT = 0.3

# Maximum total penalty that findings can impose on a dimension score.
_MAX_ISSUE_PENALTY = 24.0

# Per-unit penalty from cumulative finding severity.
_PRESSURE_PENALTY_MULTIPLIER = 2.2

# Extra penalty per additional finding beyond the first.
_EXTRA_FINDING_PENALTY = 0.8

# Findings-based score cap parameters.
_CAP_FLOOR = 60.0
_CAP_CEILING = 90.0
_CAP_PRESSURE_MULTIPLIER = 3.5


@dataclass(frozen=True)
class ScoreInputs:
    """Normalized inputs for a single dimension merge computation."""

    weighted_mean: float
    floor: float
    finding_pressure: float
    finding_count: int


@dataclass(frozen=True)
class ScoreBreakdown:
    """Named intermediate values for one merged dimension score."""

    weighted_mean: float
    floor: float
    floor_aware: float
    issue_penalty: float
    issue_cap: float | None
    final_score: float


class DimensionMergeScorer:
    """Compute pressure-adjusted merged scores for holistic review dimensions."""

    def finding_severity(
        self,
        finding: dict[str, Any],
        *,
        note: dict[str, Any] | None,
    ) -> float:
        """Compute per-finding severity used for score-pressure adjustments."""
        note_ref = note if isinstance(note, dict) else {}
        confidence = str(
            finding.get("confidence", note_ref.get("confidence", "medium"))
        ).strip().lower()
        impact_scope = str(
            finding.get("impact_scope", note_ref.get("impact_scope", "local"))
        ).strip().lower()
        fix_scope = str(
            finding.get("fix_scope", note_ref.get("fix_scope", "single_edit"))
        ).strip().lower()

        confidence_weight = _CONFIDENCE_WEIGHTS.get(confidence, 1.0)
        impact_weight = _IMPACT_SCOPE_WEIGHTS.get(impact_scope, 1.0)
        fix_weight = _FIX_SCOPE_WEIGHTS.get(fix_scope, 1.0)
        return confidence_weight * impact_weight * fix_weight

    def finding_pressure_by_dimension(
        self,
        findings: list[dict[str, Any]],
        *,
        dimension_notes: dict[str, dict[str, Any]],
    ) -> tuple[dict[str, float], dict[str, int]]:
        """Summarize how strongly findings should pull dimension scores down."""
        pressure_by_dim: dict[str, float] = {}
        count_by_dim: dict[str, int] = {}
        for finding in findings:
            dim = str(finding.get("dimension", "")).strip()
            if not dim:
                continue
            note = dimension_notes.get(dim)
            pressure_by_dim[dim] = pressure_by_dim.get(dim, 0.0) + self.finding_severity(
                finding,
                note=note if isinstance(note, dict) else None,
            )
            count_by_dim[dim] = count_by_dim.get(dim, 0) + 1
        return pressure_by_dim, count_by_dim

    def score_dimension(self, inputs: ScoreInputs) -> ScoreBreakdown:
        """Compute one merged score with explicit intermediate values."""
        floor_aware = (
            _WEIGHTED_MEAN_BLEND * inputs.weighted_mean
            + _FLOOR_BLEND_WEIGHT * inputs.floor
        )
        issue_penalty = min(
            _MAX_ISSUE_PENALTY,
            (inputs.finding_pressure * _PRESSURE_PENALTY_MULTIPLIER)
            + (max(inputs.finding_count - 1, 0) * _EXTRA_FINDING_PENALTY),
        )
        issue_adjusted = floor_aware - issue_penalty

        issue_cap: float | None = None
        if inputs.finding_count > 0:
            cap_penalty = (
                (inputs.finding_pressure * _CAP_PRESSURE_MULTIPLIER)
                + (max(inputs.finding_count - 1, 0) * _EXTRA_FINDING_PENALTY)
            )
            issue_cap = max(
                _CAP_FLOOR,
                _CAP_CEILING - cap_penalty,
            )
            issue_adjusted = min(issue_adjusted, issue_cap)

        final_score = round(max(0.0, min(100.0, issue_adjusted)), 1)
        return ScoreBreakdown(
            weighted_mean=inputs.weighted_mean,
            floor=inputs.floor,
            floor_aware=floor_aware,
            issue_penalty=issue_penalty,
            issue_cap=issue_cap,
            final_score=final_score,
        )

    def merge_scores(
        self,
        score_buckets: dict[str, list[tuple[float, float]]],
        score_raw_by_dim: dict[str, list[float]],
        finding_pressure_by_dim: dict[str, float],
        finding_count_by_dim: dict[str, int],
    ) -> dict[str, float]:
        """Compute pressure-adjusted weighted mean for each dimension."""
        merged: dict[str, float] = {}
        for key, weighted_scores in sorted(score_buckets.items()):
            if not weighted_scores:
                continue
            numerator = sum(score * weight for score, weight in weighted_scores)
            denominator = sum(weight for _, weight in weighted_scores)
            weighted_mean = numerator / max(denominator, 1.0)
            floor = min(score_raw_by_dim.get(key, [weighted_mean]))
            breakdown = self.score_dimension(
                ScoreInputs(
                    weighted_mean=weighted_mean,
                    floor=floor,
                    finding_pressure=finding_pressure_by_dim.get(key, 0.0),
                    finding_count=finding_count_by_dim.get(key, 0),
                )
            )
            merged[key] = breakdown.final_score
        return merged


__all__ = ["DimensionMergeScorer", "ScoreBreakdown", "ScoreInputs"]
