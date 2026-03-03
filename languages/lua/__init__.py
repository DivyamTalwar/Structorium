"""Lua language plugin — luacheck."""

from languages._framework.generic import generic_lang
from languages._framework.treesitter import LUA_SPEC

generic_lang(
    name="lua",
    extensions=[".lua"],
    tools=[
        {
            "label": "luacheck",
            "cmd": "luacheck . --formatter=plain 2>&1",
            "fmt": "gnu",
            "id": "luacheck_warning",
            "tier": 2,
            "fix_cmd": None,
        },
    ],
    depth="minimal",
    treesitter_spec=LUA_SPEC,
)
