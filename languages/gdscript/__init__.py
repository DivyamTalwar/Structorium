"""GDScript (Godot) language configuration for Structorium."""

from __future__ import annotations

from core._internal.text_utils import get_area
from engine.policy.zones import COMMON_ZONE_RULES, Zone, ZoneRule
from hook_registry import register_lang_hooks
from languages import register_lang
from languages._framework.base.phase_builders import (
    detector_phase_security,
    detector_phase_signature,
    detector_phase_test_coverage,
    shared_subjective_duplicates_tail,
)
from languages._framework.base.types import DetectorPhase, LangConfig
from languages._framework.treesitter.phases import all_treesitter_phases
from languages.gdscript import test_coverage as gdscript_test_coverage_hooks
from languages.gdscript.commands import get_detect_commands
from languages.gdscript.detectors.deps import (
    build_dep_graph as build_gdscript_dep_graph,
)
from languages.gdscript.extractors import (
    GDSCRIPT_FILE_EXCLUSIONS,
    extract_functions,
    find_gdscript_files,
)
from languages.gdscript.phases import _phase_coupling, _phase_structural
from languages.gdscript.review import (
    HOLISTIC_REVIEW_DIMENSIONS,
    LOW_VALUE_PATTERN,
    MIGRATION_MIXED_EXTENSIONS,
    MIGRATION_PATTERN_PAIRS,
    REVIEW_GUIDANCE,
    api_surface,
    module_patterns,
)

GDSCRIPT_ENTRY_PATTERNS = [
    "/main.gd",
    "/autoload/",
    "/addons/",
    "/tests/",
    "/test/",
]

GDSCRIPT_ZONE_RULES = [
    ZoneRule(Zone.TEST, ["/tests/", "/test/", "test_", "_test.gd"]),
    ZoneRule(Zone.CONFIG, ["/project.godot", "/.godot/", "/addons/"]),
    ZoneRule(Zone.GENERATED, ["/.import/", ".import", ".uid"]),
] + COMMON_ZONE_RULES


register_lang_hooks("gdscript", test_coverage=gdscript_test_coverage_hooks)


@register_lang("gdscript")
class GdscriptConfig(LangConfig):
    """GDScript language configuration."""

    def __init__(self):
        super().__init__(
            name="gdscript",
            extensions=[".gd"],
            exclusions=GDSCRIPT_FILE_EXCLUSIONS,
            default_src="src",
            build_dep_graph=build_gdscript_dep_graph,
            entry_patterns=GDSCRIPT_ENTRY_PATTERNS,
            barrel_names=set(),
            phases=[
                DetectorPhase("Structural analysis", _phase_structural),
                DetectorPhase("Coupling + cycles + orphaned", _phase_coupling),
                *all_treesitter_phases("gdscript"),
                detector_phase_signature(),
                detector_phase_test_coverage(),
                detector_phase_security(),
                *shared_subjective_duplicates_tail(),
            ],
            fixers={},
            get_area=get_area,
            detect_commands=get_detect_commands(),
            boundaries=[],
            typecheck_cmd="godot --headless --check-only",
            file_finder=find_gdscript_files,
            large_threshold=500,
            complexity_threshold=16,
            default_scan_profile="full",
            detect_markers=["project.godot"],
            external_test_dirs=["tests", "test"],
            test_file_extensions=[".gd"],
            review_module_patterns_fn=module_patterns,
            review_api_surface_fn=api_surface,
            review_guidance=REVIEW_GUIDANCE,
            review_low_value_pattern=LOW_VALUE_PATTERN,
            holistic_review_dimensions=HOLISTIC_REVIEW_DIMENSIONS,
            migration_pattern_pairs=MIGRATION_PATTERN_PAIRS,
            migration_mixed_extensions=MIGRATION_MIXED_EXTENSIONS,
            extract_functions=extract_functions,
            zone_rules=GDSCRIPT_ZONE_RULES,
        )
