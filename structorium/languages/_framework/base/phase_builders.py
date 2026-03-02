"""DetectorPhase builder helpers for shared framework phases."""

from __future__ import annotations

from .shared_phases import (
    phase_boilerplate_duplication,
    phase_dupes,
    phase_security,
    phase_signature,
    phase_subjective_review,
    phase_test_coverage,
)
from .types import DetectorPhase


def _phase_factory(label: str, run_fn, *, slow: bool = False):
    """Return a phase factory with explicit label/run/slow semantics."""
    def factory() -> DetectorPhase:
        return DetectorPhase(label, run_fn, slow=slow)
    return factory


SHARED_PHASE_FACTORIES = {
    "test_coverage": _phase_factory("Test coverage", phase_test_coverage),
    "security": _phase_factory("Security", phase_security),
    "signature": _phase_factory("Signature analysis", phase_signature),
    "subjective_review": _phase_factory("Subjective review", phase_subjective_review),
    "duplicates": _phase_factory("Duplicates", phase_dupes, slow=True),
    "boilerplate_duplication": _phase_factory(
        "Boilerplate duplication",
        phase_boilerplate_duplication,
        slow=True,
    ),
}


detector_phase_test_coverage = SHARED_PHASE_FACTORIES["test_coverage"]
detector_phase_security = SHARED_PHASE_FACTORIES["security"]
detector_phase_signature = SHARED_PHASE_FACTORIES["signature"]
detector_phase_subjective_review = SHARED_PHASE_FACTORIES["subjective_review"]
detector_phase_duplicates = SHARED_PHASE_FACTORIES["duplicates"]
detector_phase_boilerplate_duplication = SHARED_PHASE_FACTORIES["boilerplate_duplication"]


def shared_subjective_duplicates_tail(
    *,
    pre_duplicates: list[DetectorPhase] | None = None,
) -> list[DetectorPhase]:
    """Shared review tail: subjective review, optional custom phases, then duplicates."""
    phases = [detector_phase_subjective_review()]
    if pre_duplicates:
        phases.extend(pre_duplicates)
    phases.append(detector_phase_boilerplate_duplication())
    phases.append(detector_phase_duplicates())
    return phases


__all__ = [
    "detector_phase_boilerplate_duplication",
    "detector_phase_duplicates",
    "detector_phase_security",
    "detector_phase_signature",
    "detector_phase_subjective_review",
    "detector_phase_test_coverage",
    "SHARED_PHASE_FACTORIES",
    "shared_subjective_duplicates_tail",
]
