"""Duplicate / near-duplicate function detection via body hashing + difflib similarity.

Output is clustered: N similar functions produce 1 entry (not N^2/2 pairwise entries).
Each entry contains a representative pair for display plus the full cluster membership.
"""

import difflib
import os
import sys
import time


def _build_clusters(
    pairs: list[tuple[int, int, float, str]], n: int
) -> list[list[int]]:
    """Union-find clustering from pairwise matches. Returns list of clusters (size >= 2)."""
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i, j, _, _ in pairs:
        union(i, j)

    clusters: dict[int, list[int]] = {}
    for i in range(n):
        r = find(i)
        clusters.setdefault(r, []).append(i)
    return [c for c in clusters.values() if len(c) >= 2]


def _dupes_debug_settings() -> tuple[bool, int]:
    """Read dupes debug flags from environment."""
    debug = os.getenv("STRUCTORIUM_DUPES_DEBUG", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    try:
        debug_every = max(
            1, int(os.getenv("STRUCTORIUM_DUPES_DEBUG_EVERY", "100") or "100")
        )
    except ValueError:
        debug_every = 100
    return debug, debug_every


def _pair_key(fn_a, fn_b) -> tuple[str, str]:
    """Build a stable pair key for duplicate tracking."""
    def _identity(fn) -> str:
        end_line = getattr(fn, "end_line", None)
        if not isinstance(end_line, int):
            end_line = int(getattr(fn, "line", 0)) + int(getattr(fn, "loc", 0))
        return f"{fn.file}:{fn.name}:{fn.line}:{end_line}"

    return (_identity(fn_a), _identity(fn_b))


def _collect_exact_duplicate_pairs(
    functions, seen_pairs: set[tuple[str, str]]
) -> list[tuple[int, int, float, str]]:
    """Collect exact duplicate pairs (same normalized body hash)."""
    by_hash: dict[str, list[int]] = {}
    for idx, fn in enumerate(functions):
        by_hash.setdefault(fn.body_hash, []).append(idx)

    exact_pairs: list[tuple[int, int, float, str]] = []
    for idxs in by_hash.values():
        if len(idxs) < 2:
            continue
        for i_pos in range(len(idxs)):
            for j_pos in range(i_pos + 1, len(idxs)):
                left_idx = idxs[i_pos]
                right_idx = idxs[j_pos]
                pair_key = _pair_key(functions[left_idx], functions[right_idx])
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                exact_pairs.append((left_idx, right_idx, 1.0, "exact"))
    return exact_pairs


def _collect_near_duplicate_pairs(
    functions,
    threshold: float,
    *,
    seen_pairs: set[tuple[str, str]],
    debug: bool,
    debug_every: int,
) -> list[tuple[int, int, float, str]]:
    """Collect near-duplicate pairs using SequenceMatcher with pruning."""
    large_idx = [(idx, fn) for idx, fn in enumerate(functions) if fn.loc >= 15]
    large_idx.sort(key=lambda item: item[1].loc)
    normalized_lines = [fn.normalized.splitlines() for fn in functions]
    normalized_line_counts = [len(lines) for lines in normalized_lines]

    near_pairs: list[tuple[int, int, float, str]] = []
    near_candidates = 0
    near_ratio_calls = 0
    near_pruned_by_length = 0
    near_start = time.perf_counter()

    if debug:
        print(
            f"[dupes] start near pass: total_functions={len(functions)} "
            f"candidates_by_loc={len(large_idx)} threshold={threshold:.2f}",
            file=sys.stderr,
        )

    for i_pos in range(len(large_idx)):
        idx_a, fn_a = large_idx[i_pos]
        for j_pos in range(i_pos + 1, len(large_idx)):
            idx_b, fn_b = large_idx[j_pos]
            if fn_b.loc > fn_a.loc * 1.5:
                break
            near_candidates += 1

            pair_key = _pair_key(fn_a, fn_b)
            if pair_key in seen_pairs or fn_a.body_hash == fn_b.body_hash:
                continue

            # ratio = 2*M/(len_a+len_b), with M <= min(len_a, len_b)
            len_a = normalized_line_counts[idx_a]
            len_b = normalized_line_counts[idx_b]
            if not len_a or not len_b:
                near_pruned_by_length += 1
                continue
            max_possible = (2 * min(len_a, len_b)) / (len_a + len_b)
            if max_possible < threshold:
                near_pruned_by_length += 1
                continue

            matcher = difflib.SequenceMatcher(
                None,
                normalized_lines[idx_a],
                normalized_lines[idx_b],
                autojunk=False,
            )
            if matcher.real_quick_ratio() < threshold:
                continue
            if matcher.quick_ratio() < threshold:
                continue

            near_ratio_calls += 1
            ratio = matcher.ratio()
            if ratio >= threshold:
                seen_pairs.add(pair_key)
                near_pairs.append((idx_a, idx_b, ratio, "near-duplicate"))

        if debug and i_pos and i_pos % debug_every == 0:
            elapsed = time.perf_counter() - near_start
            print(
                f"[dupes] progress i={i_pos}/{len(large_idx)} "
                f"candidate_pairs={near_candidates} ratio_calls={near_ratio_calls} "
                f"matches={len(near_pairs)} elapsed={elapsed:.2f}s",
                file=sys.stderr,
            )

    if debug:
        elapsed = time.perf_counter() - near_start
        print(
            f"[dupes] done near pass: candidate_pairs={near_candidates} "
            f"ratio_calls={near_ratio_calls} pruned_by_length={near_pruned_by_length} "
            f"matches={len(near_pairs)} elapsed={elapsed:.2f}s",
            file=sys.stderr,
        )

    return near_pairs


def _build_duplicate_entries(
    functions, pairs: list[tuple[int, int, float, str]], clusters: list[list[int]]
) -> list[dict]:
    """Build cluster entries from matched duplicate pairs."""
    pair_lookup: dict[int, dict[int, tuple[float, str]]] = {}
    for i, j, similarity, kind in pairs:
        pair_lookup.setdefault(i, {})[j] = (similarity, kind)
        pair_lookup.setdefault(j, {})[i] = (similarity, kind)

    entries = []
    for cluster in clusters:
        best_similarity = 0.0
        best_kind = "near-duplicate"
        best_a = best_b = cluster[0]
        for left in cluster:
            for right, (similarity, kind) in pair_lookup.get(left, {}).items():
                if right in cluster and similarity > best_similarity:
                    best_similarity = similarity
                    best_kind = kind
                    best_a, best_b = left, right

        fn_a, fn_b = functions[best_a], functions[best_b]
        members = [
            {
                "file": functions[idx].file,
                "name": functions[idx].name,
                "line": functions[idx].line,
                "loc": functions[idx].loc,
            }
            for idx in cluster
        ]
        entries.append(
            {
                "fn_a": {
                    "file": fn_a.file,
                    "name": fn_a.name,
                    "line": fn_a.line,
                    "loc": fn_a.loc,
                },
                "fn_b": {
                    "file": fn_b.file,
                    "name": fn_b.name,
                    "line": fn_b.line,
                    "loc": fn_b.loc,
                },
                "similarity": round(best_similarity, 3),
                "kind": best_kind,
                "cluster_size": len(cluster),
                "cluster": members,
            }
        )
    return entries


def detect_duplicates(functions, threshold: float = 0.9) -> tuple[list[dict], int]:
    """Find duplicate/near-duplicate functions, clustered by similarity.

    Args:
        functions: list of FunctionInfo objects with .file, .name, .line, .loc,
                   .normalized, .body_hash attrs.
        threshold: similarity threshold for near-duplicates (default 0.9).

    Returns:
        (entries, total_functions) where each entry represents a cluster of
        similar functions, not a single pair.
    """
    if not functions:
        return [], 0
    debug, debug_every = _dupes_debug_settings()
    seen_pairs: set[tuple[str, str]] = set()

    pairs = _collect_exact_duplicate_pairs(functions, seen_pairs)
    pairs.extend(
        _collect_near_duplicate_pairs(
            functions,
            threshold,
            seen_pairs=seen_pairs,
            debug=debug,
            debug_every=debug_every,
        )
    )

    clusters = _build_clusters(pairs, len(functions))
    entries = _build_duplicate_entries(functions, pairs, clusters)
    return sorted(entries, key=lambda e: (-e["similarity"], -e["cluster_size"])), len(
        functions
    )
