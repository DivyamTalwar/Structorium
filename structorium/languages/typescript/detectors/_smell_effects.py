"""Extended TypeScript smell detection routines."""

from __future__ import annotations

import re


def detect_error_no_throw(
    filepath: str,
    lines: list[str],
    smell_counts: dict[str, list[dict]],
) -> None:
    """Find console.error calls not followed by throw or return."""
    for index, line in enumerate(lines):
        if "console.error" in line:
            following = "\n".join(lines[index + 1 : index + 4])
            if not re.search(r"\b(?:throw|return)\b", following):
                smell_counts["console_error_no_throw"].append(
                    {
                        "file": filepath,
                        "line": index + 1,
                        "content": line.strip()[:100],
                    }
                )


def detect_empty_if_chains(
    filepath: str,
    lines: list[str],
    smell_counts: dict[str, list[dict]],
) -> None:
    """Find if/else chains where all branches are empty."""
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if not re.match(r"(?:else\s+)?if\s*\(", stripped):
            index += 1
            continue

        if re.match(r"(?:else\s+)?if\s*\([^)]*\)\s*\{\s*\}\s*$", stripped):
            chain_start = index
            cursor = index + 1
            while cursor < len(lines):
                next_stripped = lines[cursor].strip()
                if re.match(r"else\s+if\s*\([^)]*\)\s*\{\s*\}\s*$", next_stripped):
                    cursor += 1
                    continue
                if re.match(r"(?:\}\s*)?else\s*\{\s*\}\s*$", next_stripped):
                    cursor += 1
                    continue
                break
            smell_counts["empty_if_chain"].append(
                {
                    "file": filepath,
                    "line": chain_start + 1,
                    "content": stripped[:100],
                }
            )
            index = cursor
            continue

        if re.match(r"(?:else\s+)?if\s*\([^)]*\)\s*\{\s*$", stripped):
            chain_start = index
            chain_all_empty = True
            cursor = index
            while cursor < len(lines):
                current = lines[cursor].strip()
                if cursor == chain_start:
                    if not re.match(r"(?:else\s+)?if\s*\([^)]*\)\s*\{\s*$", current):
                        chain_all_empty = False
                        break
                elif re.match(r"\}\s*else\s+if\s*\([^)]*\)\s*\{\s*$", current):
                    pass
                elif re.match(r"\}\s*else\s*\{\s*$", current):
                    pass
                elif current == "}":
                    lookahead = cursor + 1
                    while lookahead < len(lines) and lines[lookahead].strip() == "":
                        lookahead += 1
                    if lookahead < len(lines) and re.match(
                        r"else\s", lines[lookahead].strip()
                    ):
                        cursor = lookahead
                        continue
                    cursor += 1
                    break
                elif current == "":
                    cursor += 1
                    continue
                else:
                    chain_all_empty = False
                    break
                cursor += 1

            if chain_all_empty and cursor > chain_start + 1:
                smell_counts["empty_if_chain"].append(
                    {
                        "file": filepath,
                        "line": chain_start + 1,
                        "content": lines[chain_start].strip()[:100],
                    }
                )
            index = max(index + 1, cursor)
            continue

        index += 1


def detect_dead_useeffects(
    filepath: str,
    lines: list[str],
    smell_counts: dict[str, list[dict]],
    *,
    scan_code_fn,
    strip_ts_comments_fn,
) -> None:
    """Find useEffect calls with empty or comment-only bodies."""
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not re.match(r"(?:React\.)?useEffect\s*\(\s*\(\s*\)\s*=>\s*\{", stripped):
            continue

        paren_depth = 0
        end = None
        for cursor in range(index, min(index + 30, len(lines))):
            for _, ch, in_string in scan_code_fn(lines[cursor]):
                if in_string:
                    continue
                if ch == "(":
                    paren_depth += 1
                elif ch == ")":
                    paren_depth -= 1
                    if paren_depth <= 0:
                        end = cursor
                        break
            if end is not None:
                break

        if end is None:
            continue

        text = "\n".join(lines[index : end + 1])
        arrow_pos = text.find("=>")
        if arrow_pos == -1:
            continue
        brace_pos = text.find("{", arrow_pos)
        if brace_pos == -1:
            continue

        depth = 0
        body_end = None
        for cursor, ch, in_string in scan_code_fn(text, brace_pos):
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    body_end = cursor
                    break

        if body_end is None:
            continue

        body = text[brace_pos + 1 : body_end]
        if strip_ts_comments_fn(body).strip() == "":
            smell_counts["dead_useeffect"].append(
                {
                    "file": filepath,
                    "line": index + 1,
                    "content": stripped[:100],
                }
            )


def detect_swallowed_errors(
    filepath: str,
    content: str,
    lines: list[str],
    smell_counts: dict[str, list[dict]],
    *,
    scan_code_fn,
    strip_ts_comments_fn,
) -> None:
    """Find catch blocks whose only content is console.error/warn/log."""
    catch_re = re.compile(r"catch\s*\([^)]*\)\s*\{")
    for match in catch_re.finditer(content):
        brace_start = match.end() - 1
        depth = 0
        body_end = None
        for cursor, ch, in_string in scan_code_fn(
            content,
            brace_start,
            min(brace_start + 500, len(content)),
        ):
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    body_end = cursor
                    break

        if body_end is None:
            continue

        body = content[brace_start + 1 : body_end]
        body_clean = strip_ts_comments_fn(body).strip()
        if not body_clean:
            continue

        statements = [
            stmt.strip().rstrip(";")
            for stmt in re.split(r"[;\n]", body_clean)
            if stmt.strip()
        ]
        if not statements:
            continue

        all_console = all(
            re.match(r"console\.(error|warn|log)\s*\(", stmt) for stmt in statements
        )
        if all_console:
            line_no = content[: match.start()].count("\n") + 1
            smell_counts["swallowed_error"].append(
                {
                    "file": filepath,
                    "line": line_no,
                    "content": lines[line_no - 1].strip()[:100]
                    if line_no <= len(lines)
                    else "",
                }
            )


def track_brace_body(
    lines: list[str],
    start_line: int,
    *,
    scan_code_fn,
    max_scan: int = 2000,
) -> int | None:
    """Find closing brace that matches first opening brace from start_line."""
    depth = 0
    found_open = False
    for line_idx in range(start_line, min(start_line + max_scan, len(lines))):
        for _, ch, in_string in scan_code_fn(lines[line_idx]):
            if in_string:
                continue
            if ch == "{":
                depth += 1
                found_open = True
            elif ch == "}":
                depth -= 1
                if found_open and depth == 0:
                    return line_idx
    return None


__all__ = [
    "detect_dead_useeffects",
    "detect_empty_if_chains",
    "detect_error_no_throw",
    "detect_swallowed_errors",
    "track_brace_body",
]
