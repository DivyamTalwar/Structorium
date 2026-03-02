"""Rust language plugin — cargo clippy + cargo check."""

from structorium.languages._framework.generic import generic_lang
from structorium.languages._framework.treesitter import RUST_SPEC

generic_lang(
    name="rust",
    extensions=[".rs"],
    tools=[
        {
            "label": "cargo clippy",
            "cmd": "cargo clippy --message-format=json 2>&1",
            "fmt": "cargo",
            "id": "clippy_warning",
            "tier": 2,
            "fix_cmd": "cargo clippy --fix --allow-dirty",
        },
        {
            "label": "cargo check",
            "cmd": "cargo check 2>&1",
            "fmt": "gnu",
            "id": "cargo_error",
            "tier": 3,
            "fix_cmd": None,
        },
    ],
    exclude=["target"],
    depth="standard",
    detect_markers=["Cargo.toml"],
    treesitter_spec=RUST_SPEC,
)
