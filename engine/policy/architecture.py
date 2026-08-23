"""Architecture policy-as-code rules evaluated against language dependency graphs."""

from __future__ import annotations

import fnmatch
import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import state as state_mod
from languages._framework.runtime import LangRun


@dataclass(frozen=True)
class PolicyException:
    source: str
    target: str
    until: date | None = None


@dataclass(frozen=True)
class ArchitectureRule:
    id: str
    source: str
    denied: tuple[str, ...]
    tier: int = 2
    exceptions: tuple[PolicyException, ...] = field(default_factory=tuple)


class ArchitecturePolicyError(ValueError):
    """Raised when `structorium.toml` contains an invalid policy contract."""


def _as_patterns(value: object, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        raise ArchitecturePolicyError(f"{field_name} must contain a path glob")
    values = value if isinstance(value, list) else [value]
    patterns = tuple(str(item).strip() for item in values if str(item).strip())
    if not patterns:
        raise ArchitecturePolicyError(f"{field_name} must contain a path glob")
    return patterns


def _parse_exception(payload: object, rule_id: str) -> PolicyException:
    if not isinstance(payload, dict):
        raise ArchitecturePolicyError(f"rule {rule_id}: exceptions must be tables")
    until = payload.get("until")
    if until is not None and not isinstance(until, date):
        try:
            until = date.fromisoformat(str(until))
        except ValueError as exc:
            raise ArchitecturePolicyError(
                f"rule {rule_id}: exception until must be YYYY-MM-DD"
            ) from exc
    return PolicyException(
        source=str(payload.get("from", "**")),
        target=str(payload.get("to", "**")),
        until=until,
    )


def load_architecture_rules(root: Path) -> tuple[ArchitectureRule, ...]:
    """Load validated rules from `<root>/structorium.toml`."""
    policy_path = root / "structorium.toml"
    if not policy_path.is_file():
        return ()
    try:
        document = tomllib.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ArchitecturePolicyError(f"cannot parse {policy_path}: {exc}") from exc
    architecture = document.get("architecture", {})
    if not isinstance(architecture, dict) or architecture.get("enabled", True) is False:
        return ()
    raw_rules = architecture.get("rules", [])
    if not isinstance(raw_rules, list):
        raise ArchitecturePolicyError("architecture.rules must be an array of tables")
    rules: list[ArchitectureRule] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_rules, start=1):
        if not isinstance(raw, dict):
            raise ArchitecturePolicyError(f"rule {index} must be a table")
        rule_id = str(raw.get("id", f"rule-{index}")).strip()
        if not rule_id or rule_id in seen:
            raise ArchitecturePolicyError(f"duplicate or empty rule id: {rule_id!r}")
        seen.add(rule_id)
        tier = int(raw.get("tier", 2))
        if tier not in {1, 2, 3, 4}:
            raise ArchitecturePolicyError(f"rule {rule_id}: tier must be 1..4")
        rules.append(
            ArchitectureRule(
                id=rule_id,
                source=_as_patterns(raw.get("from"), field_name=f"rule {rule_id}.from")[0],
                denied=_as_patterns(raw.get("deny"), field_name=f"rule {rule_id}.deny"),
                tier=tier,
                exceptions=tuple(
                    _parse_exception(item, rule_id)
                    for item in raw.get("exceptions", [])
                ),
            )
        )
    return tuple(rules)


def _relative(value: object, root: Path) -> str:
    path = Path(str(value).replace("\\", "/"))
    if path.is_absolute():
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            return path.as_posix()
    return path.as_posix().lstrip("./")


def _matching_exception(
    rule: ArchitectureRule, source: str, target: str, today: date
) -> tuple[bool, bool]:
    for exception in rule.exceptions:
        if not (
            fnmatch.fnmatchcase(source, exception.source)
            and fnmatch.fnmatchcase(target, exception.target)
        ):
            continue
        if exception.until is None or exception.until >= today:
            return True, False
        return False, True
    return False, False


def evaluate_architecture_rules(
    graph: dict[str, dict[str, Any]],
    rules: tuple[ArchitectureRule, ...],
    *,
    root: Path,
    today: date | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Return normalized findings and the number of policy-eligible edges."""
    current_date = today or date.today()
    findings: list[dict[str, Any]] = []
    eligible = 0
    for source_value, entry in sorted(graph.items()):
        source = _relative(source_value, root)
        imports = entry.get("imports", []) if isinstance(entry, dict) else []
        for target_value in sorted(imports):
            target = _relative(target_value, root)
            for rule in rules:
                if not fnmatch.fnmatchcase(source, rule.source):
                    continue
                denied = next(
                    (pattern for pattern in rule.denied if fnmatch.fnmatchcase(target, pattern)),
                    None,
                )
                if denied is None:
                    continue
                eligible += 1
                exempt, expired = _matching_exception(
                    rule, source, target, current_date
                )
                if exempt:
                    continue
                suffix = " (an exception expired)" if expired else ""
                findings.append(
                    state_mod.make_finding(
                        "architecture_policy",
                        source,
                        f"{rule.id}:{target}",
                        tier=rule.tier,
                        confidence="high",
                        summary=f"{rule.id}: {source} must not depend on {target}{suffix}",
                        detail={
                            "rule_id": rule.id,
                            "target": target,
                            "denied_pattern": denied,
                            "expired_exception": expired,
                        },
                    )
                )
    return findings, eligible


def detect_architecture_policy(
    path: Path, lang: LangRun
) -> tuple[list[dict[str, Any]], int]:
    """Load project rules and evaluate them using the active language graph."""
    rules = load_architecture_rules(path.resolve())
    if not rules:
        return [], 0
    graph = lang.dep_graph or lang.build_dep_graph(path)
    lang.dep_graph = graph
    return evaluate_architecture_rules(graph, rules, root=path.resolve())


__all__ = [
    "ArchitecturePolicyError",
    "ArchitectureRule",
    "PolicyException",
    "detect_architecture_policy",
    "evaluate_architecture_rules",
    "load_architecture_rules",
]
