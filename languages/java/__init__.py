"""Java language plugin — pmd."""

from languages._framework.generic import generic_lang
from languages._framework.treesitter import JAVA_SPEC

generic_lang(
    name="java",
    extensions=[".java"],
    tools=[
        {
            "label": "pmd",
            "cmd": "pmd check -d . -R rulesets/java/quickstart.xml -f textcolor 2>&1",
            "fmt": "gnu",
            "id": "pmd_violation",
            "tier": 2,
            "fix_cmd": None,
        },
    ],
    exclude=["build", "target", ".gradle"],
    depth="minimal",
    detect_markers=["pom.xml", "build.gradle"],
    treesitter_spec=JAVA_SPEC,
)
