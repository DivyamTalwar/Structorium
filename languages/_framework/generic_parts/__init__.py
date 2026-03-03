"""Submodules for generic language framework composition."""

from .parsers import (
    PARSERS,
    ToolParserError,
    parse_cargo,
    parse_eslint,
    parse_gnu,
    parse_golangci,
    parse_json,
    parse_rubocop,
)
from .tool_factories import (
    make_detect_fn,
    make_detect_fn_with_runner,
    make_generic_fixer,
    make_generic_fixer_with_runner,
    make_tool_phase,
)
from .tool_runner import (
    SubprocessRun,
    ToolRunResult,
    resolve_command_argv,
    run_tool,
    run_tool_result,
)

__all__ = [
    "PARSERS",
    "SubprocessRun",
    "ToolParserError",
    "ToolRunResult",
    "make_detect_fn",
    "make_detect_fn_with_runner",
    "make_generic_fixer",
    "make_generic_fixer_with_runner",
    "make_tool_phase",
    "parse_cargo",
    "parse_eslint",
    "parse_gnu",
    "parse_golangci",
    "parse_json",
    "parse_rubocop",
    "resolve_command_argv",
    "run_tool",
    "run_tool_result",
]
