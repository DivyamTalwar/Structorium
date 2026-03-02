"""Data models for review-context construction."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, MutableMapping
from dataclasses import dataclass, field
from typing import Any


class ReviewContextSchemaError(ValueError):
    """Raised when contextual review payloads violate section-shape contracts."""


@dataclass
class SectionPayload(MutableMapping[str, Any]):
    """Named mapping wrapper for one review-context section."""

    name: str
    _data: dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value

    def __delitem__(self, key: str) -> None:
        del self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Mapping):
            return self._data == dict(other)
        return False


def _empty_section(name: str) -> SectionPayload:
    return SectionPayload(name=name)


def _coerce_section(
    *,
    section: str,
    value: object,
    strict: bool,
) -> SectionPayload:
    if isinstance(value, SectionPayload):
        if value.name == section:
            return value
        return SectionPayload(name=section, _data=value.to_dict())
    if isinstance(value, Mapping):
        return SectionPayload(name=section, _data=dict(value))
    if value is None:
        return SectionPayload(name=section)
    if strict:
        raise ReviewContextSchemaError(
            f"review context section '{section}' must be an object, got {type(value).__name__}"
        )
    return SectionPayload(name=section)


@dataclass
class ReviewContext:
    """Codebase-wide context for contextual file evaluation."""

    naming_vocabulary: SectionPayload = field(
        default_factory=lambda: _empty_section("naming_vocabulary")
    )
    error_conventions: SectionPayload = field(
        default_factory=lambda: _empty_section("error_conventions")
    )
    module_patterns: SectionPayload = field(
        default_factory=lambda: _empty_section("module_patterns")
    )
    import_graph_summary: SectionPayload = field(
        default_factory=lambda: _empty_section("import_graph_summary")
    )
    zone_distribution: SectionPayload = field(
        default_factory=lambda: _empty_section("zone_distribution")
    )
    existing_findings: SectionPayload = field(
        default_factory=lambda: _empty_section("existing_findings")
    )
    codebase_stats: SectionPayload = field(
        default_factory=lambda: _empty_section("codebase_stats")
    )
    sibling_conventions: SectionPayload = field(
        default_factory=lambda: _empty_section("sibling_conventions")
    )
    ai_debt_signals: SectionPayload = field(
        default_factory=lambda: _empty_section("ai_debt_signals")
    )
    auth_patterns: SectionPayload = field(
        default_factory=lambda: _empty_section("auth_patterns")
    )
    error_strategies: SectionPayload = field(
        default_factory=lambda: _empty_section("error_strategies")
    )

    _SECTION_NAMES = (
        "naming_vocabulary",
        "error_conventions",
        "module_patterns",
        "import_graph_summary",
        "zone_distribution",
        "existing_findings",
        "codebase_stats",
        "sibling_conventions",
        "ai_debt_signals",
        "auth_patterns",
        "error_strategies",
    )

    def __post_init__(self) -> None:
        self.normalize_sections(strict=True)

    def normalize_sections(self, *, strict: bool) -> None:
        for section in self._SECTION_NAMES:
            setattr(
                self,
                section,
                _coerce_section(section=section, value=getattr(self, section), strict=strict),
            )


@dataclass
class HolisticContext:
    """Typed seam contract for holistic review context pipelines."""

    architecture: SectionPayload = field(
        default_factory=lambda: _empty_section("architecture")
    )
    coupling: SectionPayload = field(default_factory=lambda: _empty_section("coupling"))
    conventions: SectionPayload = field(
        default_factory=lambda: _empty_section("conventions")
    )
    errors: SectionPayload = field(default_factory=lambda: _empty_section("errors"))
    abstractions: SectionPayload = field(
        default_factory=lambda: _empty_section("abstractions")
    )
    dependencies: SectionPayload = field(
        default_factory=lambda: _empty_section("dependencies")
    )
    testing: SectionPayload = field(default_factory=lambda: _empty_section("testing"))
    api_surface: SectionPayload = field(
        default_factory=lambda: _empty_section("api_surface")
    )
    structure: SectionPayload = field(default_factory=lambda: _empty_section("structure"))
    codebase_stats: SectionPayload = field(
        default_factory=lambda: _empty_section("codebase_stats")
    )
    authorization: SectionPayload = field(
        default_factory=lambda: _empty_section("authorization")
    )
    ai_debt_signals: SectionPayload = field(
        default_factory=lambda: _empty_section("ai_debt_signals")
    )
    migration_signals: SectionPayload = field(
        default_factory=lambda: _empty_section("migration_signals")
    )
    scan_evidence: SectionPayload = field(
        default_factory=lambda: _empty_section("scan_evidence")
    )

    _SECTION_NAMES = (
        "architecture",
        "coupling",
        "conventions",
        "errors",
        "abstractions",
        "dependencies",
        "testing",
        "api_surface",
        "structure",
        "codebase_stats",
        "authorization",
        "ai_debt_signals",
        "migration_signals",
        "scan_evidence",
    )

    def __post_init__(self) -> None:
        self.normalize_sections(strict=True)

    def normalize_sections(self, *, strict: bool) -> None:
        for section in self._SECTION_NAMES:
            setattr(
                self,
                section,
                _coerce_section(section=section, value=getattr(self, section), strict=strict),
            )

    @classmethod
    def from_raw(cls, payload: Mapping[str, Any] | None) -> HolisticContext:
        if payload is not None and not isinstance(payload, Mapping):
            raise ReviewContextSchemaError(
                f"holistic review context payload must be an object, got {type(payload).__name__}"
            )
        raw = payload if isinstance(payload, Mapping) else {}
        return cls(**{section: raw.get(section) for section in cls._SECTION_NAMES})

    def to_dict(self) -> dict[str, object]:
        return {section: getattr(self, section).to_dict() for section in self._SECTION_NAMES}


__all__ = [
    "HolisticContext",
    "ReviewContext",
    "ReviewContextSchemaError",
    "SectionPayload",
]
