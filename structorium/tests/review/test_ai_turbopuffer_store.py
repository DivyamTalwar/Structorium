"""Tests for Turbopuffer adapter SDK compatibility behavior."""

from __future__ import annotations

from types import SimpleNamespace

from structorium.intelligence.ai.turbopuffer_store import TurbopufferStore


class _LegacyCompatNamespace:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def query(self, **kwargs):
        self.calls.append(dict(kwargs))
        if "include_vectors" in kwargs:
            raise TypeError("query() got an unexpected keyword argument 'include_vectors'")
        return {
            "rows": [
                {
                    "id": "chunk-a",
                    "distance": 0.2,
                    "attributes": {"file": "src/main.ts", "chunk_index": 0, "content": "x"},
                }
            ]
        }


class _ModelDumpRow:
    def model_dump(self) -> dict[str, object]:
        return {
            "id": "chunk-b",
            "distance": 0.1,
            "file": "src/utils/lib.ts",
            "chunk_index": 1,
            "content": "y",
        }


def test_query_falls_back_when_include_vectors_is_unsupported():
    namespace = _LegacyCompatNamespace()
    store = object.__new__(TurbopufferStore)
    store._namespace = namespace

    hits = store.query([0.3, 0.4], top_k=5)

    assert len(namespace.calls) == 2
    assert "include_vectors" in namespace.calls[0]
    assert "include_vectors" not in namespace.calls[1]
    assert namespace.calls[1]["distance_metric"] == "cosine_distance"
    assert namespace.calls[1]["rank_by"][0] == "vector"
    assert namespace.calls[1]["rank_by"][1] == "ANN"
    assert len(hits) == 1
    assert hits[0].row_id == "chunk-a"
    assert hits[0].attributes["file"] == "src/main.ts"


def test_query_coerces_model_rows_to_dict():
    store = object.__new__(TurbopufferStore)
    store._namespace = SimpleNamespace(
        query=lambda **_kwargs: SimpleNamespace(rows=[_ModelDumpRow()])
    )

    hits = store.query([0.1], top_k=1)

    assert len(hits) == 1
    assert hits[0].row_id == "chunk-b"
    assert hits[0].attributes["file"] == "src/utils/lib.ts"
    assert hits[0].score > 0.0
