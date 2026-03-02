"""Elixir language plugin — mix credo."""

from structorium.languages._framework.generic import generic_lang
from structorium.languages._framework.treesitter import ELIXIR_SPEC

generic_lang(
    name="elixir",
    extensions=[".ex", ".exs"],
    tools=[
        {
            "label": "mix credo",
            "cmd": "mix credo --format=json",
            "fmt": "json",
            "id": "credo_issue",
            "tier": 2,
            "fix_cmd": None,
        },
    ],
    exclude=["_build", "deps"],
    depth="shallow",
    detect_markers=["mix.exs"],
    treesitter_spec=ELIXIR_SPEC,
)
