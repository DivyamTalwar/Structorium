from datetime import date
from pathlib import Path

import pytest

from engine.policy.architecture import (
    ArchitecturePolicyError,
    ArchitectureRule,
    PolicyException,
    evaluate_architecture_rules,
    load_architecture_rules,
)


def _graph(root: Path):
    return {
        str(root / "src/domain/orders.py"): {
            "imports": [str(root / "src/web/routes.py")]
        }
    }


def test_policy_detects_forbidden_dependency(tmp_path: Path) -> None:
    rules = (ArchitectureRule("domain-purity", "src/domain/**", ("src/web/**",)),)

    findings, eligible = evaluate_architecture_rules(
        _graph(tmp_path), rules, root=tmp_path
    )

    assert eligible == 1
    assert findings[0]["detector"] == "architecture_policy"
    assert findings[0]["detail"]["rule_id"] == "domain-purity"


def test_active_exception_suppresses_and_expired_exception_reports(tmp_path: Path) -> None:
    active = ArchitectureRule(
        "domain-purity",
        "src/domain/**",
        ("src/web/**",),
        exceptions=(PolicyException("**", "**", date(2030, 1, 1)),),
    )
    expired = ArchitectureRule(
        "domain-purity",
        "src/domain/**",
        ("src/web/**",),
        exceptions=(PolicyException("**", "**", date(2020, 1, 1)),),
    )

    assert evaluate_architecture_rules(
        _graph(tmp_path), (active,), root=tmp_path, today=date(2026, 1, 1)
    )[0] == []
    finding = evaluate_architecture_rules(
        _graph(tmp_path), (expired,), root=tmp_path, today=date(2026, 1, 1)
    )[0][0]
    assert finding["detail"]["expired_exception"] is True


def test_loads_toml_and_rejects_duplicate_ids(tmp_path: Path) -> None:
    policy = tmp_path / "structorium.toml"
    policy.write_text(
        """
[architecture]
enabled = true
[[architecture.rules]]
id = "domain-purity"
from = "src/domain/**"
deny = ["src/web/**", "src/db/**"]
tier = 1
"""
    )
    assert load_architecture_rules(tmp_path)[0].tier == 1

    policy.write_text(
        policy.read_text()
        + '\n[[architecture.rules]]\nid = "domain-purity"\nfrom = "a/**"\ndeny = "b/**"\n'
    )
    with pytest.raises(ArchitecturePolicyError, match="duplicate"):
        load_architecture_rules(tmp_path)
