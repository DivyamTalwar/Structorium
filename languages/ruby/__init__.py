"""Ruby language plugin — rubocop."""

from languages._framework.generic import generic_lang
from languages._framework.treesitter import RUBY_SPEC

generic_lang(
    name="ruby",
    extensions=[".rb"],
    tools=[
        {
            "label": "rubocop",
            "cmd": "rubocop --format=json",
            "fmt": "rubocop",
            "id": "rubocop_offense",
            "tier": 2,
            "fix_cmd": "rubocop --auto-correct",
        },
    ],
    exclude=["vendor"],
    depth="shallow",
    detect_markers=["Gemfile"],
    treesitter_spec=RUBY_SPEC,
)
