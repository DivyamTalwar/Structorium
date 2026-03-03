"""Nim language plugin — nim check."""

from languages._framework.generic import generic_lang
from languages._framework.treesitter import NIM_SPEC

generic_lang(
    name="nim",
    extensions=[".nim"],
    tools=[
        {
            "label": "nim check",
            "cmd": "nim check $(find . -name '*.nim' -maxdepth 2 | head -20) 2>&1",
            "fmt": "gnu",
            "id": "nim_error",
            "tier": 3,
            "fix_cmd": None,
        },
    ],
    depth="minimal",
    detect_markers=["*.nimble"],
    treesitter_spec=NIM_SPEC,
)
