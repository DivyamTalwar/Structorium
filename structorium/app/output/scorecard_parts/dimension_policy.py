"""Scorecard dimension ordering and language policy constants."""

from __future__ import annotations

_SCORECARD_MAX_DIMENSIONS = 20
_DEFAULT_ELEGANCE_COMPONENTS: tuple[str, ...] = (
    "High elegance",
    "Mid elegance",
    "Low elegance",
)
_ELEGANCE_COMPONENTS_BY_LANG: dict[str, tuple[str, ...]] = {
    "python": _DEFAULT_ELEGANCE_COMPONENTS,
    "typescript": _DEFAULT_ELEGANCE_COMPONENTS,
    "csharp": _DEFAULT_ELEGANCE_COMPONENTS,
}

# Display ordering preferences for subjective dimensions on the scorecard.
# These are cosmetic only — they control sort priority when the scorecard
# needs to truncate, not which dimensions appear.  The actual dimensions
# shown are derived dynamically from dimension_scores in state.
_SUBJECTIVE_SCORECARD_ORDER_DEFAULT: tuple[str, ...] = (
    "Elegance",
    "Abstraction fit",
    "Error consistency",
    "AI generated debt",
    "Cross-module arch",
    "Convention drift",
    "Dep health",
    "Test strategy",
    "Structure nav",
    "Design coherence",
    "API coherence",
    "Auth consistency",
    "Stale migration",
    "Init coupling",
    "Naming quality",
    "Logic clarity",
    "Type safety",
    "Contracts",
)
_SUBJECTIVE_SCORECARD_ORDER_BY_LANG: dict[str, tuple[str, ...]] = {
    "python": (
        "Elegance",
        "Abstraction fit",
        "Error consistency",
        "AI generated debt",
        "Cross-module arch",
        "Convention drift",
        "Dep health",
        "Test strategy",
        "Structure nav",
        "Design coherence",
    ),
    "typescript": (
        "Elegance",
        "Abstraction fit",
        "Error consistency",
        "AI generated debt",
        "Cross-module arch",
        "Convention drift",
        "API coherence",
        "Auth consistency",
        "Stale migration",
        "Structure nav",
        "Design coherence",
    ),
    "csharp": (
        "Elegance",
        "Abstraction fit",
        "Error consistency",
        "AI generated debt",
        "Cross-module arch",
        "Convention drift",
        "API coherence",
        "Auth consistency",
        "Stale migration",
        "Structure nav",
        "Design coherence",
    ),
}
_MECHANICAL_SCORECARD_DIMENSIONS: tuple[str, ...] = (
    "File health",
    "Code quality",
    "Duplication",
    "Test health",
    "Security",
)


def _compose_scorecard_dimensions(subjective_order: tuple[str, ...]) -> tuple[str, ...]:
    merged: list[str] = []
    for name in (*_MECHANICAL_SCORECARD_DIMENSIONS, *subjective_order):
        if name not in merged:
            merged.append(name)
    return tuple(merged[:_SCORECARD_MAX_DIMENSIONS])


_SCORECARD_DIMENSIONS_BY_LANG: dict[str, tuple[str, ...]] = {
    "python": _compose_scorecard_dimensions(_SUBJECTIVE_SCORECARD_ORDER_BY_LANG["python"]),
    "typescript": _compose_scorecard_dimensions(_SUBJECTIVE_SCORECARD_ORDER_BY_LANG["typescript"]),
    "csharp": _compose_scorecard_dimensions(_SUBJECTIVE_SCORECARD_ORDER_BY_LANG["csharp"]),
}


__all__ = [
    "_DEFAULT_ELEGANCE_COMPONENTS",
    "_ELEGANCE_COMPONENTS_BY_LANG",
    "_MECHANICAL_SCORECARD_DIMENSIONS",
    "_SCORECARD_DIMENSIONS_BY_LANG",
    "_SCORECARD_MAX_DIMENSIONS",
    "_SUBJECTIVE_SCORECARD_ORDER_BY_LANG",
    "_SUBJECTIVE_SCORECARD_ORDER_DEFAULT",
]
