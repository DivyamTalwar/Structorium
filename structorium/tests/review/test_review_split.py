"""Tests verifying the review/ package split — all imports work, no circular deps."""

from __future__ import annotations

import importlib
import sys

import pytest

from structorium.intelligence import review


class TestReviewImports:
    """Verify all public names are importable from structorium.intelligence.review."""

    def test_all_exports_importable(self):
        """Every name in __all__ is importable."""
        for name in review.__all__:
            assert hasattr(review, name), f"Missing export: {name}"

    def test_key_public_names(self):
        """Key public names are available."""
        key_names = [
            "ReviewContext",
            "build_review_context",
            "prepare_review",
            "import_review_findings",
            "select_files_for_review",
            "DIMENSIONS",
            "generate_remediation_plan",
            "build_investigation_batches",
        ]
        for name in key_names:
            assert hasattr(review, name), f"Missing key public name: {name}"
            obj = getattr(review, name)
            # Constants should be non-empty collections; callables should be callable
            if name.isupper() or name.startswith("DEFAULT_"):
                assert obj, f"Key constant {name} should be non-empty"
            else:
                assert callable(obj), f"Key name {name} should be callable"


class TestSubmoduleImports:
    """Each submodule can be imported independently."""

    @pytest.mark.parametrize(
        "module",
        [
            "structorium.intelligence.review.dimensions.holistic",
            "structorium.intelligence.review.dimensions.lang",
            "structorium.intelligence.review.context",
            "structorium.intelligence.review.selection",
            "structorium.intelligence.review.prepare",
            "structorium.intelligence.review.importing.per_file",
            "structorium.intelligence.review.importing.holistic",
            "structorium.intelligence.review.importing.shared",
            "structorium.intelligence.review.remediation",
        ],
    )
    def test_submodule_importable(self, module):
        mod = importlib.import_module(module)
        assert mod is not None

    def test_no_circular_import(self):
        """Fresh import of structorium.intelligence.review succeeds without circular import errors."""
        # Remove cached modules to force fresh import
        to_remove = [k for k in sys.modules if k.startswith("structorium.intelligence.review")]
        removed = {}
        for k in to_remove:
            removed[k] = sys.modules.pop(k)
        try:
            # If we get here, no circular import
            imported = importlib.import_module("structorium.intelligence.review")
            assert hasattr(imported, "__all__")
        finally:
            # Restore removed modules
            sys.modules.update(removed)
