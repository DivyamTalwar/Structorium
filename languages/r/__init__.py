"""R language plugin — lintr + tree-sitter."""

from languages._framework.generic import generic_lang
from languages._framework.treesitter import R_SPEC

generic_lang(
    name="r",
    extensions=[".R", ".r"],
    tools=[
        {
            "label": "lintr",
            "cmd": (
                'Rscript -e \'cat(paste(capture.output('
                'lintr::lint_dir(".", show_notifications=FALSE)'
                '), collapse="\\n"))\''
            ),
            "fmt": "gnu",
            "id": "lintr_lint",
            "tier": 2,
            "fix_cmd": None,
        },
    ],
    exclude=[".Rhistory", ".RData", ".Rproj.user", "renv", "packrat"],
    depth="shallow",
    detect_markers=["DESCRIPTION", ".Rproj"],
    default_src="R",
    treesitter_spec=R_SPEC,
)
