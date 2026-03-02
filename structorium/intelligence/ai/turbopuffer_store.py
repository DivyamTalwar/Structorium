"""Turbopuffer vector storage adapter."""

from __future__ import annotations

from dataclasses import dataclass

from .settings import AISettings


class TurbopufferUnavailableError(RuntimeError):
    """Raised when Turbopuffer SDK/client is unavailable."""


@dataclass(frozen=True)
class VectorHit:
    row_id: str
    score: float
    attributes: dict[str, object]


class TurbopufferStore:
    """Wrapper around Turbopuffer SDK with resilient output coercion."""

    def __init__(self, settings: AISettings) -> None:
        if not settings.turbopuffer_api_key:
            raise TurbopufferUnavailableError("TURBOPUFFER_API_KEY is required")

        try:
            from turbopuffer import Turbopuffer  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - environment-dependent
            raise TurbopufferUnavailableError(
                "Missing turbopuffer SDK. Install with `pip install turbopuffer`."
            ) from exc

        kwargs: dict[str, object] = {"api_key": settings.turbopuffer_api_key}
        if settings.turbopuffer_region:
            kwargs["region"] = settings.turbopuffer_region
        self._client = Turbopuffer(**kwargs)
        self._namespace = self._client.namespace(settings.turbopuffer_namespace)

    def upsert(self, rows: list[dict[str, object]]) -> None:
        if not rows:
            return
        self._namespace.write(
            upsert_rows=rows,
            distance_metric="cosine_distance",
        )

    def query(self, vector: list[float], *, top_k: int) -> list[VectorHit]:
        if not vector:
            return []

        base_query_kwargs = {
            "rank_by": ("vector", "ANN", vector),
            "distance_metric": "cosine_distance",
            "top_k": top_k,
            "include_attributes": True,
        }
        try:
            # Older SDKs accept include_vectors, newer versions dropped it.
            raw = self._namespace.query(
                **base_query_kwargs,
                include_vectors=False,
            )
        except TypeError as exc:
            if "include_vectors" not in str(exc):
                raise
            raw = self._namespace.query(**base_query_kwargs)

        rows_raw = _extract_rows(raw)
        out: list[VectorHit] = []
        for row_raw in rows_raw:
            row = _coerce_row_dict(row_raw)
            if row is None:
                continue
            row_id = str(row.get("id", ""))
            if not row_id:
                continue
            score = _coerce_score(row)
            attrs = _extract_attributes(row)
            out.append(VectorHit(row_id=row_id, score=score, attributes=attrs))
        return out


def _extract_rows(payload: object) -> list[object]:
    if isinstance(payload, dict):
        rows = payload.get("rows")
        if isinstance(rows, list):
            return rows
    rows = getattr(payload, "rows", None)
    if isinstance(rows, list):
        return rows
    return []


def _coerce_row_dict(row: object) -> dict[str, object] | None:
    if isinstance(row, dict):
        return dict(row)
    for name in ("model_dump", "to_dict", "dict"):
        method = getattr(row, name, None)
        if callable(method):
            dumped = method()
            if isinstance(dumped, dict):
                return dict(dumped)
    return None


def _extract_attributes(row: dict[str, object]) -> dict[str, object]:
    attrs = row.get("attributes")
    if isinstance(attrs, dict):
        return dict(attrs)
    # Some SDK versions return flattened attribute fields.
    return {
        key: value
        for key, value in row.items()
        if key
        not in {
            "id",
            "vector",
            "distance",
            "score",
            "similarity",
            "dist",
            "attributes",
        }
    }


def _coerce_score(row: dict[str, object]) -> float:
    for key in ("score", "similarity", "distance", "dist"):
        raw = row.get(key)
        if isinstance(raw, int | float):
            value = float(raw)
            # Turbopuffer usually returns distance for ANN queries; invert to
            # make higher score better while preserving relative ordering.
            if key in {"distance", "dist"}:
                return 1.0 - value
            return value
    return 0.0


__all__ = [
    "TurbopufferStore",
    "TurbopufferUnavailableError",
    "VectorHit",
]
