"""Microbenchmark the cold and warm objective-scan manifest path."""

from __future__ import annotations

import tempfile
from pathlib import Path
from time import perf_counter

from core.runtime_state import make_runtime_context, runtime_scope
from engine.planning.incremental_cache import prepare_scan_cache, store_scan_cache
from languages._framework.base.types import DetectorPhase, LangConfig
from languages._framework.runtime import make_lang_run


def main(file_count: int = 10_000) -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for index in range(file_count):
            (root / f"module_{index:05d}.py").write_text(f"VALUE = {index}\n")
        language = make_lang_run(
            LangConfig(
                name="benchmark",
                extensions=[".py"],
                exclusions=[],
                default_src=".",
                build_dep_graph=lambda _: {},
                entry_patterns=[],
                barrel_names=set(),
                file_finder=lambda _: [str(path) for path in root.glob("*.py")],
            )
        )
        phase = DetectorPhase("benchmark", lambda *_: ([], {}))
        runtime = make_runtime_context()
        runtime.project_root = root
        with runtime_scope(runtime):
            started = perf_counter()
            cold = prepare_scan_cache(
                root, language, [phase], profile="ci", include_slow=False,
                zone_overrides=None,
            )
            cold_seconds = perf_counter() - started
            store_scan_cache(cold, [], {})
            started = perf_counter()
            warm = prepare_scan_cache(
                root, language, [phase], profile="ci", include_slow=False,
                zone_overrides=None,
            )
            warm_seconds = perf_counter() - started
        print({
            "files": file_count,
            "cold_seconds": round(cold_seconds, 4),
            "warm_seconds": round(warm_seconds, 4),
            "hit": warm.hit,
        })


if __name__ == "__main__":
    main()
