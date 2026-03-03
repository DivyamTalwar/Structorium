"""F# language plugin — dotnet build."""

from languages._framework.generic import generic_lang
from languages._framework.treesitter import FSHARP_SPEC

generic_lang(
    name="fsharp",
    extensions=[".fs", ".fsi", ".fsx"],
    tools=[
        {
            "label": "dotnet build",
            "cmd": "dotnet build --no-restore 2>&1",
            "fmt": "gnu",
            "id": "fsharp_error",
            "tier": 3,
            "fix_cmd": None,
        },
    ],
    depth="minimal",
    detect_markers=["*.fsproj"],
    treesitter_spec=FSHARP_SPEC,
)
