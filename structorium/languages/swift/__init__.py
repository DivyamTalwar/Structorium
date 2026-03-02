"""Swift language plugin — swiftlint."""

from structorium.languages._framework.generic import generic_lang
from structorium.languages._framework.treesitter import SWIFT_SPEC

generic_lang(
    name="swift",
    extensions=[".swift"],
    tools=[
        {
            "label": "swiftlint",
            "cmd": "swiftlint lint --reporter json",
            "fmt": "json",
            "id": "swiftlint_violation",
            "tier": 2,
            "fix_cmd": "swiftlint --fix",
        },
    ],
    depth="shallow",
    detect_markers=["Package.swift"],
    treesitter_spec=SWIFT_SPEC,
)
