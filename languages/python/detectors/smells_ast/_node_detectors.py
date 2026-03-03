"""AST detectors that operate on function/class nodes."""

from __future__ import annotations

import ast

from languages.python.detectors.smells_ast._shared import (
    _is_docstring,
    _is_return_none,
)


def _is_test_file(filepath: str) -> bool:
    """Return True when a path clearly points to a test module."""
    normalized = filepath.replace("\\", "/")
    return normalized.startswith("tests/") or "/tests/" in normalized


def _detect_monster_functions(filepath: str, node: ast.AST) -> list[dict]:
    """Flag functions longer than 150 LOC."""
    if not (hasattr(node, "end_lineno") and node.end_lineno):
        return []
    loc = node.end_lineno - node.lineno + 1
    if loc > 150:
        return [
            {
                "file": filepath,
                "line": node.lineno,
                "content": f"{node.name}() — {loc} LOC",
            }
        ]
    return []


def _detect_dead_functions(filepath: str, node: ast.AST) -> list[dict]:
    """Flag functions whose body is only pass, return, or return None."""
    if node.decorator_list:
        return []
    body = node.body
    if len(body) == 1:
        stmt = body[0]
        if isinstance(stmt, ast.Pass) or _is_return_none(stmt):
            return [
                {
                    "file": filepath,
                    "line": node.lineno,
                    "content": f"{node.name}() — body is only {ast.dump(stmt)[:40]}",
                }
            ]
    elif len(body) == 2:
        first, second = body
        if not _is_docstring(first):
            return []
        if isinstance(second, ast.Pass):
            desc = "docstring + pass"
        elif _is_return_none(second):
            desc = "docstring + return None"
        else:
            return []
        return [
            {
                "file": filepath,
                "line": node.lineno,
                "content": f"{node.name}() — {desc}",
            }
        ]
    return []


def _detect_deferred_imports(filepath: str, node: ast.AST) -> list[dict]:
    """Flag function-level imports (possible circular import workarounds)."""
    if _is_test_file(filepath):
        return []
    _SKIP_MODULES = ("typing", "typing_extensions", "__future__")
    for child in ast.walk(node):
        if (
            not isinstance(child, ast.Import | ast.ImportFrom)
            or child.lineno <= node.lineno
        ):
            continue
        module = getattr(child, "module", None) or ""
        if module in _SKIP_MODULES:
            continue
        names = ", ".join(a.name for a in child.names[:3])
        if len(child.names) > 3:
            names += f", +{len(child.names) - 3}"
        return [
            {
                "file": filepath,
                "line": child.lineno,
                "content": f"import {module or names} inside {node.name}()",
            }
        ]
    return []


def _detect_inline_classes(filepath: str, node: ast.AST) -> list[dict]:
    """Flag classes defined inside functions."""
    results: list[dict] = []
    for child in node.body:
        if isinstance(child, ast.ClassDef):
            results.append(
                {
                    "file": filepath,
                    "line": child.lineno,
                    "content": f"class {child.name} defined inside {node.name}()",
                }
            )
    return results


_FUNC_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
_BLOCK_ATTRS = ("body", "handlers", "orelse", "finalbody")


def _walk_inner_defs(
    body: list[ast.AST], depth: int, inner_defs: list[ast.AST],
) -> int:
    """Recursively collect inner function/lambda defs and return max nesting depth."""
    max_depth = 0
    for child in body:
        if isinstance(child, _FUNC_TYPES):
            inner_defs.append(child)
            current_depth = depth + 1
            max_depth = max(max_depth, current_depth)
            child_body = getattr(child, "body", None)
            if isinstance(child_body, list):
                max_depth = max(
                    max_depth,
                    _walk_inner_defs(child_body, current_depth, inner_defs),
                )
            elif isinstance(child, ast.Lambda):
                max_depth = max(
                    max_depth,
                    _collect_nested_lambdas(child, current_depth, inner_defs),
                )
        else:
            for attr in _BLOCK_ATTRS:
                sub_body = getattr(child, attr, None)
                if isinstance(sub_body, list):
                    max_depth = max(
                        max_depth, _walk_inner_defs(sub_body, depth, inner_defs),
                    )
    return max_depth


def _collect_nested_lambdas(
    parent: ast.Lambda, depth: int, inner_defs: list[ast.AST],
) -> int:
    """Walk a lambda's expression body for nested lambdas."""
    max_depth = depth
    for sub in ast.walk(parent.body):
        if isinstance(sub, ast.Lambda) and sub is not parent:
            inner_defs.append(sub)
            max_depth = max(max_depth, depth + 1)
    return max_depth


def _format_inner_def_names(inner_defs: list[ast.AST]) -> str:
    """Format inner def names for the finding content string."""
    names = [
        getattr(d, "name", "<lambda>")
        for d in inner_defs[:5]
        if isinstance(d, ast.FunctionDef | ast.AsyncFunctionDef)
    ]
    names_str = ", ".join(names) if names else "<lambdas>"
    if len(inner_defs) > 5:
        names_str += ", ..."
    return names_str


def _detect_nested_closures(filepath: str, node: ast.AST) -> list[dict]:
    """Flag functions with deeply nested inner defs or too many inner defs total."""
    inner_defs: list[ast.AST] = []
    max_depth = _walk_inner_defs(node.body, 0, inner_defs)

    if max_depth < 2 and len(inner_defs) < 3:
        return []
    return [
        {
            "file": filepath,
            "line": node.lineno,
            "content": (
                f"{node.name}() — {len(inner_defs)} inner defs"
                f" (depth {max_depth}): {_format_inner_def_names(inner_defs)}"
            ),
        }
    ]


def _collect_single_list_assignments(body: list[ast.AST]) -> dict[str, int]:
    """Return {name: lineno} for `x = [single_value]` assignments."""
    result: dict[str, int] = {}
    for stmt in body:
        if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
            continue
        target = stmt.targets[0]
        if (
            isinstance(target, ast.Name)
            and isinstance(stmt.value, ast.List)
            and len(stmt.value.elts) == 1
        ):
            result[target.id] = stmt.lineno
    return result


def _find_subscript_zero_refs(
    node: ast.AST, candidate_names: set[str],
) -> set[str]:
    """Find names from candidate_names accessed as x[0] inside nested functions."""
    used: set[str] = set()
    for child in ast.walk(node):
        if child is node or not isinstance(child, _FUNC_TYPES):
            continue
        for sub in ast.walk(child):
            if not isinstance(sub, ast.Subscript):
                continue
            if not isinstance(sub.value, ast.Name):
                continue
            if sub.value.id not in candidate_names:
                continue
            if isinstance(sub.slice, ast.Constant) and sub.slice.value == 0:
                used.add(sub.value.id)
    return used


def _detect_mutable_ref_hack(filepath: str, node: ast.AST) -> list[dict]:
    """Flag mutable-list-as-ref hacks: x = [value] then x[0] inside a nested function."""
    single_list_names = _collect_single_list_assignments(node.body)
    if not single_list_names:
        return []

    used_names = _find_subscript_zero_refs(node, set(single_list_names))
    return [
        {
            "file": filepath,
            "line": single_list_names[name],
            "content": (
                f"{name} = [v] in {node.name}()"
                " — mutable-list ref hack (use nonlocal or a dataclass)"
            ),
        }
        for name in sorted(used_names)
    ]


# Node types that contribute to cyclomatic complexity.
_DECISION_TYPES = (
    ast.If, ast.IfExp, ast.For, ast.AsyncFor, ast.While,
    ast.ExceptHandler, ast.With, ast.AsyncWith, ast.Assert,
)


def _compute_cyclomatic_complexity(node: ast.AST) -> int:
    """Compute cyclomatic complexity for a function AST node."""
    complexity = 1
    for child in ast.walk(node):
        if isinstance(child, _DECISION_TYPES):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            complexity += len(child.values) - 1
    return complexity


def _detect_high_cyclomatic_complexity(filepath: str, node: ast.AST) -> list[dict]:
    """Flag functions with cyclomatic complexity > 12."""
    complexity = _compute_cyclomatic_complexity(node)
    if complexity > 12:
        return [
            {
                "file": filepath,
                "line": node.lineno,
                "content": f"{node.name}() — cyclomatic complexity {complexity}",
            }
        ]
    return []


def _detect_lru_cache_mutable(
    filepath: str,
    node: ast.AST,
    tree: ast.Module,
) -> list[dict]:
    """Flag @lru_cache/@cache functions that reference module-level mutable variables.

    Finds globals referenced in the function body that aren't in the parameter list,
    checking if those names are assigned to mutable values at module level.
    """
    # Check if this function has @lru_cache or @cache decorator
    has_cache = False
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name) and dec.id in ("lru_cache", "cache"):
            has_cache = True
        elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name):
            if dec.func.id in ("lru_cache", "cache"):
                has_cache = True
        elif isinstance(dec, ast.Attribute) and dec.attr in ("lru_cache", "cache"):
            has_cache = True
    if not has_cache:
        return []

    # Get parameter names
    param_names = set()
    for arg in node.args.args + node.args.posonlyargs + node.args.kwonlyargs:
        param_names.add(arg.arg)
    if node.args.vararg:
        param_names.add(node.args.vararg.arg)
    if node.args.kwarg:
        param_names.add(node.args.kwarg.arg)

    # Collect module-level mutable assignments
    module_mutables = set()
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name) and isinstance(
                    stmt.value, ast.List | ast.Dict | ast.Set | ast.Call
                ):
                    module_mutables.add(target.id)
        elif (
            isinstance(stmt, ast.AnnAssign)
            and stmt.target
            and isinstance(stmt.target, ast.Name)
        ):
            if stmt.value and isinstance(
                stmt.value, ast.List | ast.Dict | ast.Set | ast.Call
            ):
                module_mutables.add(stmt.target.id)

    # Find Name references in function body that point to module-level mutables
    for child in ast.walk(node):
        if (
            isinstance(child, ast.Name)
            and child.id in module_mutables
            and child.id not in param_names
        ):
            return [
                {
                    "file": filepath,
                    "line": node.lineno,
                    "content": f"@lru_cache on {node.name}() reads mutable global '{child.id}'",
                }
            ]
    return []
