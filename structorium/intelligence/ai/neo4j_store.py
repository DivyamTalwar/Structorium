"""Neo4j graph adapter for repository structure."""

from __future__ import annotations

from dataclasses import dataclass

from .settings import AISettings


class Neo4jUnavailableError(RuntimeError):
    """Raised when Neo4j credentials/driver are unavailable."""


@dataclass(frozen=True)
class GraphNeighbors:
    path: str
    imports: list[str]
    importers: list[str]
    fan_in: int
    fan_out: int


class Neo4jStore:
    """Manage file/import graph synchronization and neighbor lookups."""

    def __init__(self, settings: AISettings) -> None:
        if not settings.has_neo4j:
            raise Neo4jUnavailableError(
                "NEO4J_URI + NEO4J_USERNAME + NEO4J_PASSWORD are required"
            )
        try:
            from neo4j import GraphDatabase  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise Neo4jUnavailableError(
                "Missing neo4j driver. Install with `pip install neo4j`."
            ) from exc

        self._database = settings.neo4j_database
        self._driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )

    def close(self) -> None:
        try:
            self._driver.close()
        except Exception:  # pragma: no cover - best effort boundary
            return

    def upsert_graph(
        self,
        *,
        files: list[dict[str, object]],
        edges: list[dict[str, str]],
        run_id: str,
    ) -> None:
        if not files:
            return
        with self._driver.session(database=self._database) as session:
            session.run(
                """
                UNWIND $files AS row
                MERGE (f:File {path: row.path})
                SET
                    f.loc = row.loc,
                    f.language = row.language,
                    f.sha1 = row.sha1,
                    f.updated_at = timestamp(),
                    f.run_id = $run_id
                """,
                files=files,
                run_id=run_id,
            )
            if edges:
                session.run(
                    """
                    UNWIND $edges AS row
                    MATCH (src:File {path: row.source})
                    MATCH (dst:File {path: row.target})
                    MERGE (src)-[r:IMPORTS]->(dst)
                    SET
                        r.updated_at = timestamp(),
                        r.run_id = $run_id
                    """,
                    edges=edges,
                    run_id=run_id,
                )

    def neighbors(self, paths: list[str], *, limit: int = 10) -> list[GraphNeighbors]:
        if not paths:
            return []
        with self._driver.session(database=self._database) as session:
            result = session.run(
                """
                UNWIND $paths AS p
                MATCH (f:File {path: p})
                OPTIONAL MATCH (f)-[:IMPORTS]->(out:File)
                WITH f, collect(DISTINCT out.path)[0..$limit] AS imports
                OPTIONAL MATCH (incoming:File)-[:IMPORTS]->(f)
                RETURN
                    f.path AS path,
                    imports AS imports,
                    collect(DISTINCT incoming.path)[0..$limit] AS importers,
                    COUNT { (f)<-[:IMPORTS]-() } AS fan_in,
                    COUNT { (f)-[:IMPORTS]->() } AS fan_out
                """,
                paths=paths,
                limit=limit,
            )
            out: list[GraphNeighbors] = []
            for row in result:
                out.append(
                    GraphNeighbors(
                        path=str(row.get("path", "")),
                        imports=_clean_path_list(row.get("imports")),
                        importers=_clean_path_list(row.get("importers")),
                        fan_in=_safe_int(row.get("fan_in")),
                        fan_out=_safe_int(row.get("fan_out")),
                    )
                )
            return out


def _clean_path_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item:
            out.append(item)
    return out


def _safe_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int | float):
        return int(value)
    return 0


__all__ = ["GraphNeighbors", "Neo4jStore", "Neo4jUnavailableError"]
