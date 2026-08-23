from pathlib import Path

from engine.planning.incremental_cache import prepare_scan_cache, store_scan_cache
from languages._framework.base.types import DetectorPhase, LangConfig
from languages._framework.runtime import make_lang_run


def _language(root: Path):
    def files(_: Path) -> list[str]:
        return [str(path) for path in sorted(root.glob("*.py"))]

    return make_lang_run(
        LangConfig(
            name="fixture",
            extensions=[".py"],
            exclusions=[],
            default_src=".",
            build_dep_graph=lambda _: {},
            entry_patterns=[],
            barrel_names=set(),
            file_finder=files,
        )
    )


def _phase() -> DetectorPhase:
    return DetectorPhase("fixture", lambda path, lang: ([], {}))


def _lookup(root: Path, monkeypatch):
    monkeypatch.setenv("STRUCTORIUM_ROOT", str(root))
    from core.runtime_state import make_runtime_context, runtime_scope

    runtime = make_runtime_context()
    runtime.project_root = root
    with runtime_scope(runtime):
        return prepare_scan_cache(
            root,
            _language(root),
            [_phase()],
            profile="ci",
            include_slow=False,
            zone_overrides=None,
        )


def test_round_trip_cache_hit(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "app.py").write_text("value = 1\n")
    first = _lookup(tmp_path, monkeypatch)
    assert not first.hit
    store_scan_cache(first, [{"detector": "fixture"}], {"fixture": 1})

    second = _lookup(tmp_path, monkeypatch)
    assert second.hit
    assert second.findings == [{"detector": "fixture"}]


def test_source_change_invalidates_result(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "app.py"
    source.write_text("value = 1\n")
    first = _lookup(tmp_path, monkeypatch)
    store_scan_cache(first, [], {})

    source.write_text("value = 200\n")
    second = _lookup(tmp_path, monkeypatch)
    assert not second.hit
    assert second.key != first.key


def test_corrupt_cache_fails_open(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "app.py").write_text("value = 1\n")
    cache = tmp_path / ".structorium" / "cache" / "objective-scan-v1.json"
    cache.parent.mkdir(parents=True)
    cache.write_text("not-json")

    assert not _lookup(tmp_path, monkeypatch).hit
