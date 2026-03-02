"""Intelligence-layer packages: review, narrative, and subjective integrity workflows.

Subpackages
-----------
narrative
    Computed coaching context (phase, headline, actions, reminders).
    Entry point: ``compute_narrative()``

review
    Subjective code review preparation, import, and context building.
    Entry point: ``prepare_review()`` / ``import_review_findings()``

integrity
    Lightweight integrity checks for subjective scoring.
    Entry point: ``is_subjective_review_open()``
"""

from __future__ import annotations

# Note: subpackages are NOT eagerly imported here to avoid circular
# dependencies (state ↔ intelligence). Import from subpackages directly:
#   from structorium.intelligence.narrative.core import compute_narrative
#   from structorium.intelligence.review import prepare_review

__all__ = [
    "integrity",
    "narrative",
    "review",
]
