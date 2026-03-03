#!/usr/bin/env python3
"""Test-only Roslyn adapter that emits a Roslyn-like dependency payload.

This allows Roslyn-integration/parity tests to run in local environments
without a compiled Roslyn CLI by reusing the heuristic graph builder.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        print("{}", end="")
        return 0

    target_path = Path(sys.argv[1]).resolve()

    # Ensure we never recurse into this adapter again via env-driven Roslyn command.
    os.environ.pop("STRUCTORIUM_CSHARP_ROSLYN_CMD", None)

    from languages.csharp.detectors.deps import build_dep_graph

    graph = build_dep_graph(target_path)
    payload = {
        "files": [
            {
                "file": source,
                "imports": sorted(
                    target
                    for target in entry.get("imports", set())
                    if isinstance(target, str) and target
                ),
            }
            for source, entry in sorted(graph.items())
        ]
    }
    print(json.dumps(payload), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
