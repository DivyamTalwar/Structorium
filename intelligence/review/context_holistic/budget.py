"""Sizing and truncation helpers for holistic context payloads."""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from pathlib import Path

from core.discovery_api import rel
from intelligence.review.context import file_excerpt

_DEF_SIGNATURE_RE = re.compile(
    r"(?:^|\n)\s*(?:async\s+def|def|async\s+function|function)\s+\w+\s*\(([^)]*)\)",
    re.MULTILINE,
)
_TS_PASSTHROUGH_RE = re.compile(
    r"\bfunction\s+(\w+)\s*\([^)]*\)\s*\{\s*return\s+(\w+)\s*\(",
    re.MULTILINE,
)
_INTERFACE_RE = re.compile(
    r"\binterface\s+([A-Za-z_]\w*)\b|\bclass\s+([A-Za-z_]\w*Protocol)\b"
)
_IMPLEMENTS_RE = re.compile(r"\bclass\s+\w+\s+implements\s+([^{:\n]+)")
_INHERITS_RE = re.compile(r"\bclass\s+\w+\s*(?:\(([^)\n]+)\)\s*:|:\s*([^\n{]+))")
_CHAIN_RE = re.compile(r"\b(?:\w+\.){2,}\w+\b")
_CONFIG_BAG_RE = re.compile(
    r"\b(?:config|configs|options|opts|params|ctx|context)\b",
    re.IGNORECASE,
)


def _count_signature_params(params_blob: str) -> int:
    """Best-effort parameter counting for function signatures."""
    cleaned = params_blob.strip()
    if not cleaned:
        return 0
    parts = [part.strip() for part in cleaned.split(",") if part.strip()]
    filtered = [part for part in parts if part not in {"self", "cls", "this"}]
    return len(filtered)


def _extract_type_names(blob: str) -> list[str]:
    """Extract candidate type names from implements/inherits blobs."""
    names: list[str] = []
    for raw in re.split(r"[,\s()]+", blob):
        token = raw.strip()
        if not token:
            continue
        token = token.split(".")[-1]
        token = token.split("<")[0]
        token = token.strip(":")
        if not token or not re.match(r"^[A-Za-z_]\w*$", token):
            continue
        names.append(token)
    return names


def _score_clamped(raw: float) -> int:
    """Clamp score-like values to [0, 100]."""
    return int(max(0, min(100, round(raw))))


def _strip_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    """Strip a leading docstring from a function/method body."""
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        return body[1:]
    return body


def _python_passthrough_target(stmt: ast.stmt) -> str | None:
    """Return passthrough call target when stmt is `return target(...)`."""
    if not isinstance(stmt, ast.Return):
        return None
    value = stmt.value
    if not isinstance(value, ast.Call):
        return None
    target = value.func
    if isinstance(target, ast.Name):
        return target.id
    return None


def _find_python_passthrough_wrappers(tree: ast.Module) -> list[tuple[str, str]]:
    """Find Python wrapper pairs via AST traversal."""
    wrappers: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue

        body = _strip_docstring(list(node.body))
        if len(body) != 1:
            continue

        target_name = _python_passthrough_target(body[0])
        if target_name and node.name != target_name:
            wrappers.append((node.name, target_name))
    return wrappers


def _is_delegation_stmt(stmt: ast.stmt) -> str | None:
    """Return the delegate attribute name if *stmt* is a pure delegation.

    Matches patterns like:
    - ``return self.x.method(...)``
    - ``return self.x``  (property forwarding)
    - ``self.x.method(...)``  (void delegation)
    """
    # Unwrap Expr nodes (void calls like ``self.x.do()``)
    if isinstance(stmt, ast.Expr):
        value = stmt.value
    elif isinstance(stmt, ast.Return) and stmt.value is not None:
        value = stmt.value
    else:
        return None

    # ``self.x.method(...)`` or ``self.x(...)``
    if isinstance(value, ast.Call):
        value = value.func

    # Walk the attribute chain to find ``self.<attr>``
    node = value
    depth = 0
    while isinstance(node, ast.Attribute):
        node = node.value
        depth += 1
    if depth < 1 or not isinstance(node, ast.Name) or node.id != "self":
        return None

    # The first attribute after self — walk back down from the outermost
    # Attribute to find the one whose .value is the Name("self") node.
    first = value
    while isinstance(first, ast.Attribute) and isinstance(first.value, ast.Attribute):
        first = first.value
    if isinstance(first, ast.Attribute) and isinstance(first.value, ast.Name):
        return first.attr
    return None


def _find_delegation_heavy_classes(tree: ast.Module) -> list[dict]:
    """Find classes where most methods delegate to a single inner object."""
    results: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue

        methods: list[ast.FunctionDef | ast.AsyncFunctionDef] = [
            child
            for child in node.body
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
            and child.name != "__init__"
        ]
        if len(methods) <= 3:
            continue

        # Track which methods delegate to which attribute
        delegating_methods: dict[str, list[str]] = {}  # attr -> [method_names]
        for method in methods:
            body = _strip_docstring(list(method.body))
            if len(body) != 1:
                continue
            attr = _is_delegation_stmt(body[0])
            if attr:
                delegating_methods.setdefault(attr, []).append(method.name)

        if not delegating_methods:
            continue

        # Use the most common delegate target
        top_attr = max(delegating_methods, key=lambda a: len(delegating_methods[a]))
        delegate_count = len(delegating_methods[top_attr])
        ratio = delegate_count / len(methods)
        if ratio > 0.5:
            results.append(
                {
                    "class_name": node.name,
                    "line": node.lineno,
                    "delegation_ratio": round(ratio, 2),
                    "method_count": len(methods),
                    "delegate_count": delegate_count,
                    "delegate_target": top_attr,
                    "sample_methods": delegating_methods[top_attr][:5],
                }
            )
    return results


def _find_facade_modules(tree: ast.Module, *, loc: int) -> dict | None:
    """Detect modules where >70% of public names come from imports."""
    import_names: set[str] = set()
    defined_names: set[str] = set()

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name.split(".")[-1]
                import_names.add(name)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    continue
                name = alias.asname or alias.name
                import_names.add(name)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            defined_names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            defined_names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    continue
                if isinstance(target, ast.Name):
                    defined_names.add(target.id)

    # Remove private names
    public_imports = {n for n in import_names if not n.startswith("_")}
    public_defs = {n for n in defined_names if not n.startswith("_")}

    total_public = len(public_imports | public_defs)
    if total_public < 3:
        return None

    # Re-exported = imported names that aren't shadowed by a local definition
    re_exported = public_imports - public_defs
    re_export_ratio = len(re_exported) / total_public

    if re_export_ratio < 0.7 or len(public_defs) > 3:
        return None

    return {
        "re_export_ratio": round(re_export_ratio, 2),
        "defined_symbols": len(public_defs),
        "re_exported_symbols": len(re_exported),
        "samples": sorted(re_exported)[:5],
        "loc": loc,
    }


def _collect_typed_dict_defs(
    tree: ast.Module, accumulator: dict[str, set[str]]
) -> None:
    """Collect TypedDict class definitions from a single file's AST."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        is_typed_dict = any(
            (isinstance(b, ast.Name) and b.id == "TypedDict")
            or (isinstance(b, ast.Attribute) and b.attr == "TypedDict")
            for b in node.bases
        )
        if not is_typed_dict:
            continue
        fields: set[str] = set()
        for child in node.body:
            if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                fields.add(child.target.id)
        if fields:
            accumulator[node.name] = fields


_VIOLATION_METHODS = frozenset({"get", "setdefault", "pop"})


def _find_typed_dict_usage_violations(
    parsed_trees: dict[str, ast.Module],
    typed_dicts: dict[str, set[str]],
) -> list[dict]:
    """Find .get()/.setdefault()/.pop() calls on TypedDict-annotated variables.

    *parsed_trees* maps absolute file paths to pre-parsed ASTs (built during
    the main collection loop to avoid redundant parses).

    Returns a list of violation dicts with file, typed_dict_name, violation_type,
    line, field (when extractable), and count.
    """
    if not typed_dicts:
        return []

    violations: list[dict] = []
    for filepath, tree in parsed_trees.items():
        rpath = rel(filepath)

        # Collect variable names annotated with known TypedDict types
        typed_vars: dict[str, str] = {}  # var_name -> TypedDict name
        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                ann = node.annotation
                ann_name = None
                if isinstance(ann, ast.Name):
                    ann_name = ann.id
                elif isinstance(ann, ast.Attribute):
                    ann_name = ann.attr
                if ann_name in typed_dicts:
                    typed_vars[node.target.id] = ann_name
            # Also check function param annotations
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                for arg in node.args.args + node.args.kwonlyargs:
                    ann = arg.annotation
                    if ann is None:
                        continue
                    ann_name = None
                    if isinstance(ann, ast.Name):
                        ann_name = ann.id
                    elif isinstance(ann, ast.Attribute):
                        ann_name = ann.attr
                    if ann_name in typed_dicts:
                        typed_vars[arg.arg] = ann_name

        if not typed_vars:
            continue

        # Scan for violation calls — collect per (td_name, method, field)
        hits: list[tuple[str, str, str | None, int]] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute):
                continue
            if func.attr not in _VIOLATION_METHODS:
                continue
            if not isinstance(func.value, ast.Name) or func.value.id not in typed_vars:
                continue
            td_name = typed_vars[func.value.id]
            # Extract the field name from the first argument if it's a string constant
            field: str | None = None
            if node.args and isinstance(node.args[0], ast.Constant):
                val = node.args[0].value
                if isinstance(val, str):
                    field = val
            hits.append((td_name, func.attr, field, node.lineno))

        # Group by (td_name, method, field) for compact reporting
        groups: dict[tuple[str, str, str | None], list[int]] = {}
        for td_name, method, field, lineno in hits:
            groups.setdefault((td_name, method, field), []).append(lineno)

        for (td_name, method, field), lines in groups.items():
            entry: dict = {
                "file": rpath,
                "typed_dict_name": td_name,
                "violation_type": method,
                "line": lines[0],
                "count": len(lines),
            }
            if field is not None:
                entry["field"] = field
            violations.append(entry)

    return violations


def _abstractions_context(file_contents: dict[str, str]) -> dict:
    util_files = []
    wrappers_by_file: list[dict[str, object]] = []
    interface_declarations: dict[str, set[str]] = defaultdict(set)
    implementations: dict[str, set[str]] = defaultdict(set)
    indirection_hotspots: list[dict[str, object]] = []
    wide_param_bags: list[dict[str, object]] = []
    delegation_classes: list[dict] = []
    facade_modules: list[dict] = []
    typed_dict_defs: dict[str, set[str]] = {}
    parsed_trees: dict[str, ast.Module] = {}

    total_function_signatures = 0
    total_wrappers = 0

    for filepath, content in file_contents.items():
        rpath = rel(filepath)
        loc = len(content.splitlines())
        basename = Path(rpath).stem.lower()
        if basename in {"utils", "helpers", "util", "helper", "common", "misc"}:
            util_files.append(
                {
                    "file": rpath,
                    "loc": loc,
                    "excerpt": file_excerpt(filepath) or "",
                }
            )

        # ── Regex-based detectors (all languages) ────────────
        signatures = _DEF_SIGNATURE_RE.findall(content)
        total_function_signatures += len(signatures)

        ts_wrappers = [
            (wrapper, target)
            for wrapper, target in _TS_PASSTHROUGH_RE.findall(content)
            if wrapper != target
        ]

        for match in _INTERFACE_RE.finditer(content):
            iface = match.group(1) or match.group(2)
            if iface:
                interface_declarations[iface].add(rpath)

        for match in _IMPLEMENTS_RE.finditer(content):
            for iface in _extract_type_names(match.group(1)):
                implementations[iface].add(rpath)
        for match in _INHERITS_RE.finditer(content):
            blob = match.group(1) or match.group(2) or ""
            for iface in _extract_type_names(blob):
                implementations[iface].add(rpath)

        chain_matches = _CHAIN_RE.findall(content)
        max_chain_depth = max((token.count(".") for token in chain_matches), default=0)
        if max_chain_depth >= 3 or len(chain_matches) >= 6:
            indirection_hotspots.append(
                {
                    "file": rpath,
                    "max_chain_depth": max_chain_depth,
                    "chain_count": len(chain_matches),
                }
            )

        wide_functions = sum(
            1 for params_blob in signatures if _count_signature_params(params_blob) >= 7
        )
        bag_mentions = len(_CONFIG_BAG_RE.findall(content))
        if wide_functions > 0 or bag_mentions >= 10:
            wide_param_bags.append(
                {
                    "file": rpath,
                    "wide_functions": wide_functions,
                    "config_bag_mentions": bag_mentions,
                }
            )

        # ── AST-based detectors (Python files only) ──────────
        try:
            tree = ast.parse(content)
        except SyntaxError:
            tree = None

        if tree is not None:
            parsed_trees[filepath] = tree

            py_wrappers = _find_python_passthrough_wrappers(tree)

            for entry in _find_delegation_heavy_classes(tree):
                delegation_classes.append({"file": rpath, **entry})

            facade_result = _find_facade_modules(tree, loc=loc)
            if facade_result is not None:
                facade_modules.append({"file": rpath, **facade_result})

            _collect_typed_dict_defs(tree, typed_dict_defs)
        else:
            py_wrappers = []

        wrapper_pairs = py_wrappers + ts_wrappers
        if wrapper_pairs:
            total_wrappers += len(wrapper_pairs)
            wrappers_by_file.append(
                {
                    "file": rpath,
                    "count": len(wrapper_pairs),
                    "samples": [f"{w}->{t}" for w, t in wrapper_pairs[:5]],
                }
            )

    # ── Post-loop cross-file analysis ─────────────────────────

    one_impl_interfaces: list[dict[str, object]] = []
    for iface, declared_in in interface_declarations.items():
        implemented_in = sorted(implementations.get(iface, set()))
        if len(implemented_in) != 1:
            continue
        one_impl_interfaces.append(
            {
                "interface": iface,
                "declared_in": sorted(declared_in),
                "implemented_in": implemented_in,
            }
        )

    typed_dict_violations = _find_typed_dict_usage_violations(
        parsed_trees, typed_dict_defs
    )[:20]
    total_typed_dict_violations = sum(v.get("count", 1) for v in typed_dict_violations)
    typed_dict_violation_files = {v["file"] for v in typed_dict_violations}

    # ── Sort ──────────────────────────────────────────────────

    wrappers_by_file.sort(key=lambda item: -int(item["count"]))
    indirection_hotspots.sort(
        key=lambda item: (-int(item["max_chain_depth"]), -int(item["chain_count"]))
    )
    wide_param_bags.sort(
        key=lambda item: (
            -int(item["wide_functions"]),
            -int(item["config_bag_mentions"]),
        )
    )
    one_impl_interfaces.sort(key=lambda item: str(item["interface"]))
    delegation_classes.sort(key=lambda d: -d["delegation_ratio"])
    delegation_classes = delegation_classes[:20]
    facade_modules.sort(key=lambda d: -d["re_export_ratio"])
    facade_modules = facade_modules[:20]

    # ── Sub-axis scoring ──────────────────────────────────────

    wrapper_rate = total_wrappers / max(total_function_signatures, 1)
    abstraction_leverage = _score_clamped(
        100 - (wrapper_rate * 120) - (len(util_files) * 1.5)
    )
    indirection_cost = _score_clamped(
        100
        - (sum(item["max_chain_depth"] for item in indirection_hotspots[:20]) * 2.5)
        - (sum(item["wide_functions"] for item in wide_param_bags[:20]) * 2.0)
    )
    interface_honesty = _score_clamped(100 - (len(one_impl_interfaces) * 8))

    top10_delegation = delegation_classes[:10]
    avg_delegation_ratio = (
        sum(d["delegation_ratio"] for d in top10_delegation) / len(top10_delegation)
        if top10_delegation
        else 0.0
    )
    delegation_density = _score_clamped(
        100 - (avg_delegation_ratio * 80) - (len(delegation_classes) * 5)
    )
    avg_facade_ratio = (
        sum(f["re_export_ratio"] for f in facade_modules[:10]) / len(facade_modules[:10])
        if facade_modules
        else 0.0
    )
    definition_directness = _score_clamped(
        100 - (len(facade_modules) * 8) - (avg_facade_ratio * 50)
    )
    type_discipline = _score_clamped(
        100
        - (len(typed_dict_violation_files) * 6)
        - (total_typed_dict_violations * 1.5)
    )

    util_files = sorted(util_files, key=lambda item: -item["loc"])[:20]
    context: dict[str, object] = {
        "util_files": util_files,
        "summary": {
            "wrapper_rate": round(wrapper_rate, 3),
            "total_wrappers": total_wrappers,
            "total_function_signatures": total_function_signatures,
            "one_impl_interface_count": len(one_impl_interfaces),
            "indirection_hotspot_count": len(indirection_hotspots),
            "wide_param_bag_count": len(wide_param_bags),
            "delegation_heavy_class_count": len(delegation_classes),
            "facade_module_count": len(facade_modules),
            "typed_dict_violation_count": total_typed_dict_violations,
        },
        "sub_axes": {
            "abstraction_leverage": abstraction_leverage,
            "indirection_cost": indirection_cost,
            "interface_honesty": interface_honesty,
            "delegation_density": delegation_density,
            "definition_directness": definition_directness,
            "type_discipline": type_discipline,
        },
    }
    if wrappers_by_file:
        context["pass_through_wrappers"] = wrappers_by_file[:20]
    if one_impl_interfaces:
        context["one_impl_interfaces"] = one_impl_interfaces[:20]
    if indirection_hotspots:
        context["indirection_hotspots"] = indirection_hotspots[:20]
    if wide_param_bags:
        context["wide_param_bags"] = wide_param_bags[:20]
    if delegation_classes:
        context["delegation_heavy_classes"] = delegation_classes
    if facade_modules:
        context["facade_modules"] = facade_modules
    if typed_dict_violations:
        context["typed_dict_violations"] = typed_dict_violations
    return context


def _codebase_stats(file_contents: dict[str, str]) -> dict[str, int]:
    total_loc = sum(len(content.splitlines()) for content in file_contents.values())
    return {
        "total_files": len(file_contents),
        "total_loc": total_loc,
    }
