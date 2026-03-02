"""Perl language plugin — perlcritic."""

from structorium.languages._framework.generic import generic_lang
from structorium.languages._framework.treesitter import PERL_SPEC

generic_lang(
    name="perl",
    extensions=[".pl", ".pm"],
    tools=[
        {
            "label": "perlcritic",
            "cmd": "perlcritic --quiet --severity=1 . 2>&1",
            "fmt": "gnu",
            "id": "perlcritic_violation",
            "tier": 2,
            "fix_cmd": None,
        },
    ],
    depth="minimal",
    treesitter_spec=PERL_SPEC,
)
