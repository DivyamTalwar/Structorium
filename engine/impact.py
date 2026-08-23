"""Bounded, deterministic dependency-impact exploration algorithms."""

from __future__ import annotations

import hashlib
import json
from collections import deque
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any, Literal, TypedDict

ImpactDirection = Literal["dependents", "dependencies", "both"]


class ImpactEntry(TypedDict):
    path: str
    direction: Literal["dependents", "dependencies"]
    distance: int
    witness: list[str]


class ImpactEdge(TypedDict):
    source: str
    target: str


class ImpactReport(TypedDict):
    seeds: list[str]
    direction: ImpactDirection
    max_depth: int
    max_nodes: int
    truncated: bool
    entries: list[ImpactEntry]
    edges: list[ImpactEdge]
    node_count: int


def _normalize_path(value: object, project_root: Path) -> str:
    raw = str(value or ".").replace("\\", "/")
    candidate = Path(raw)
    if candidate.is_absolute():
        try:
            raw = str(candidate.resolve().relative_to(project_root.resolve()))
        except (OSError, ValueError):
            raw = candidate.as_posix()
    normalized = PurePosixPath(raw).as_posix()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.rstrip("/") or "."


def normalize_graph(
    graph: Mapping[str, Mapping[str, Any]], project_root: Path
) -> dict[str, set[str]]:
    """Normalize heterogeneous language graphs into source -> dependency edges."""
    normalized: dict[str, set[str]] = {}
    for raw_source, raw_entry in graph.items():
        source = _normalize_path(raw_source, project_root)
        normalized.setdefault(source, set())
        imports = raw_entry.get("imports", set())
        if not isinstance(imports, (set, list, tuple, frozenset)):
            continue
        for raw_target in imports:
            target = _normalize_path(raw_target, project_root)
            normalized[source].add(target)
            normalized.setdefault(target, set())
    return normalized


def resolve_seeds(nodes: set[str], targets: list[str], project_root: Path) -> list[str]:
    """Resolve exact file or directory-prefix targets against normalized graph nodes."""
    seeds: set[str] = set()
    for target in targets:
        normalized = _normalize_path(target, project_root)
        if normalized in nodes:
            seeds.add(normalized)
            continue
        prefix = normalized.rstrip("/") + "/"
        seeds.update(node for node in nodes if node.startswith(prefix))
    return sorted(seeds)


def _reverse_graph(graph: Mapping[str, set[str]]) -> dict[str, set[str]]:
    reverse = {node: set() for node in graph}
    for source, dependencies in graph.items():
        for dependency in dependencies:
            reverse.setdefault(dependency, set()).add(source)
    return reverse


def _walk(
    adjacency: Mapping[str, set[str]],
    seeds: list[str],
    *,
    direction: Literal["dependents", "dependencies"],
    max_depth: int,
    budget: int,
) -> tuple[list[ImpactEntry], bool]:
    witnesses = {seed: [seed] for seed in seeds}
    distances = {seed: 0 for seed in seeds}
    queue = deque(seeds)
    entries: list[ImpactEntry] = []

    while queue:
        current = queue.popleft()
        distance = distances[current]
        if distance >= max_depth:
            continue
        for neighbor in sorted(adjacency.get(current, set())):
            if neighbor in distances:
                continue
            if len(entries) >= budget:
                return entries, True
            distances[neighbor] = distance + 1
            witnesses[neighbor] = [*witnesses[current], neighbor]
            entries.append(
                {
                    "path": neighbor,
                    "direction": direction,
                    "distance": distance + 1,
                    "witness": witnesses[neighbor],
                }
            )
            queue.append(neighbor)
    return entries, False


def analyze_impact(
    graph: Mapping[str, Mapping[str, Any]],
    targets: list[str],
    *,
    project_root: Path,
    direction: ImpactDirection = "both",
    max_depth: int = 3,
    max_nodes: int = 200,
) -> ImpactReport:
    """Explore dependency blast radius with shortest-path witnesses and hard bounds."""
    if max_depth < 1:
        raise ValueError("max_depth must be at least 1")
    if max_nodes < 1:
        raise ValueError("max_nodes must be at least 1")
    if direction not in {"dependents", "dependencies", "both"}:
        raise ValueError(f"unsupported impact direction: {direction}")

    normalized = normalize_graph(graph, project_root)
    seeds = resolve_seeds(set(normalized), targets, project_root)
    if not seeds:
        raise ValueError(f"no dependency graph nodes matched: {', '.join(targets)}")
    seed_truncated = len(seeds) > max_nodes
    seeds = seeds[:max_nodes]

    entries: list[ImpactEntry] = []
    truncated = seed_truncated
    directions: list[Literal["dependents", "dependencies"]] = (
        ["dependents", "dependencies"] if direction == "both" else [direction]
    )
    reverse = _reverse_graph(normalized)
    for selected in directions:
        remaining = max_nodes - len(seeds) - len(entries)
        if remaining <= 0:
            truncated = True
            break
        adjacency = reverse if selected == "dependents" else normalized
        found, did_truncate = _walk(
            adjacency,
            seeds,
            direction=selected,
            max_depth=max_depth,
            budget=remaining,
        )
        entries.extend(found)
        truncated = truncated or did_truncate

    entries.sort(key=lambda item: (item["distance"], item["direction"], item["path"]))
    visible = {*seeds, *(item["path"] for item in entries)}
    edges = [
        {"source": source, "target": target}
        for source in sorted(visible)
        for target in sorted(normalized.get(source, set()))
        if target in visible
    ]
    return {
        "seeds": seeds,
        "direction": direction,
        "max_depth": max_depth,
        "max_nodes": max_nodes,
        "truncated": truncated,
        "entries": entries,
        "edges": edges,
        "node_count": len(visible),
    }


def render_impact_text(report: ImpactReport) -> str:
    """Render a concise operator-facing impact report."""
    lines = [
        "Dependency impact",
        f"Seeds: {', '.join(report['seeds'])}",
        f"Visible nodes: {report['node_count']} (depth <= {report['max_depth']})",
    ]
    for entry in report["entries"]:
        witness = " -> ".join(entry["witness"])
        lines.append(
            f"[{entry['direction']} d={entry['distance']}] {entry['path']} via {witness}"
        )
    if report["truncated"]:
        lines.append(f"TRUNCATED at {report['max_nodes']} impacted nodes")
    return "\n".join(lines) + "\n"


def render_impact_json(report: ImpactReport) -> str:
    """Render stable machine-readable impact evidence."""
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def _mermaid_id(path: str) -> str:
    return "n" + hashlib.sha1(path.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]


def _mermaid_label(path: str) -> str:
    return path.replace('"', "'")


def render_impact_mermaid(report: ImpactReport) -> str:
    """Render a review-ready Mermaid dependency graph."""
    nodes = sorted(
        {*report["seeds"], *(entry["path"] for entry in report["entries"])}
    )
    lines = ["flowchart LR"]
    for node in nodes:
        lines.append(f'  {_mermaid_id(node)}["{_mermaid_label(node)}"]')
    for edge in report["edges"]:
        lines.append(f"  {_mermaid_id(edge['source'])} --> {_mermaid_id(edge['target'])}")
    for seed in report["seeds"]:
        lines.append(f"  class {_mermaid_id(seed)} seed")
    lines.append("  classDef seed fill:#ffd166,stroke:#111,stroke-width:3px")
    if report["truncated"]:
        lines.append(f"  %% truncated at {report['max_nodes']} impacted nodes")
    return "\n".join(lines) + "\n"


__all__ = [
    "ImpactDirection",
    "ImpactEdge",
    "ImpactEntry",
    "ImpactReport",
    "analyze_impact",
    "normalize_graph",
    "render_impact_json",
    "render_impact_mermaid",
    "render_impact_text",
    "resolve_seeds",
]
