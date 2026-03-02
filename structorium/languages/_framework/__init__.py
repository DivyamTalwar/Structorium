"""Shared language-framework internals.

This package contains framework code used by all language plugins:
- config/runtime contracts
- plugin discovery/registration state
- shared detect-command factories
- shared finding factories and facade helpers
"""

from __future__ import annotations

from typing import Any

from .base.types import (
    BoundaryRule,
    DetectorPhase,
    FixerConfig,
    FixResult,
    LangConfig,
    LangValueSpec,
)


def make_lang_config(*args: Any, **kwargs: Any):
    from .resolution import make_lang_config as _make_lang_config

    return _make_lang_config(*args, **kwargs)


def get_lang(*args: Any, **kwargs: Any):
    from .resolution import get_lang as _get_lang

    return _get_lang(*args, **kwargs)


def auto_detect_lang(*args: Any, **kwargs: Any):
    from .resolution import auto_detect_lang as _auto_detect_lang

    return _auto_detect_lang(*args, **kwargs)


def available_langs(*args: Any, **kwargs: Any):
    from .resolution import available_langs as _available_langs

    return _available_langs(*args, **kwargs)

__all__ = [
    "BoundaryRule",
    "DetectorPhase",
    "FixerConfig",
    "FixResult",
    "LangConfig",
    "LangValueSpec",
    "auto_detect_lang",
    "available_langs",
    "get_lang",
    "make_lang_config",
]
