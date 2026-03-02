#!/usr/bin/env python3
"""Deterministic Roslyn stub used by CI integration tests.

It emits a minimal graph payload accepted by the C# dependency parser.
"""

from __future__ import annotations

import json


def main() -> None:
    # Returning an empty edges list is intentional: parser accepts it and
    # language detector will fall back to heuristic graph construction.
    print(json.dumps({"edges": []}))


if __name__ == "__main__":
    main()
