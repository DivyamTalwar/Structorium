"""Tests for Neo4j adapter query compatibility."""

from __future__ import annotations

from intelligence.ai.neo4j_store import Neo4jStore


class _FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, query: str, **kwargs):
        self.calls.append((query, dict(kwargs)))
        return [
            {
                "path": "src/main.ts",
                "imports": ["src/utils/lib.ts"],
                "importers": [],
                "fan_in": 2,
                "fan_out": 1,
            }
        ]


class _FakeDriver:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    def session(self, *, database: str):
        assert database == "neo4j"
        return self._session


def test_neighbors_uses_count_pattern_syntax():
    session = _FakeSession()
    store = object.__new__(Neo4jStore)
    store._database = "neo4j"
    store._driver = _FakeDriver(session)

    neighbors = store.neighbors(["src/main.ts"], limit=8)

    assert len(neighbors) == 1
    assert neighbors[0].path == "src/main.ts"
    assert neighbors[0].fan_in == 2
    assert neighbors[0].fan_out == 1
    assert session.calls
    cypher = session.calls[0][0]
    assert "COUNT { (f)<-[:IMPORTS]-() } AS fan_in" in cypher
    assert "COUNT { (f)-[:IMPORTS]->() } AS fan_out" in cypher
