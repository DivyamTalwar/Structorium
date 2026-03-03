"""Scala language plugin — scalac warnings."""

from languages._framework.generic import generic_lang
from languages._framework.treesitter import SCALA_SPEC

generic_lang(
    name="scala",
    extensions=[".scala"],
    tools=[
        {
            "label": "scalac",
            "cmd": "scalac -Xlint -d /tmp $(find . -name '*.scala') 2>&1",
            "fmt": "gnu",
            "id": "scalac_warning",
            "tier": 3,
            "fix_cmd": None,
        },
    ],
    exclude=["target", ".bsp"],
    depth="minimal",
    detect_markers=["build.sbt"],
    treesitter_spec=SCALA_SPEC,
)
