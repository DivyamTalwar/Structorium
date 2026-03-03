"""Tests for C# parsing helpers: brace matching, expression end, param splitting."""

from __future__ import annotations

from languages.csharp._parse_helpers import (
    extract_csharp_params,
    extract_csharp_return_annotation,
    find_expression_end,
    find_matching_brace,
    split_params,
)

# ── find_matching_brace ───────────────────────────────────────


def test_find_matching_brace_simple():
    content = "{ return 1; }"
    assert find_matching_brace(content, 0) == 12


def test_find_matching_brace_nested():
    content = "{ if (x) { return 1; } }"
    assert find_matching_brace(content, 0) == 23


def test_find_matching_brace_deeply_nested():
    content = "{ { { } } }"
    assert find_matching_brace(content, 0) == 10


def test_find_matching_brace_inner():
    """Finding matching brace starting at inner open brace."""
    content = "{ { inner } outer }"
    assert find_matching_brace(content, 2) == 10


def test_find_matching_brace_skips_strings():
    """Braces inside strings are not counted."""
    content = '{ var s = "{ }"; }'
    assert find_matching_brace(content, 0) == 17


def test_find_matching_brace_skips_single_quote_strings():
    content = "{ var c = '{'; }"
    assert find_matching_brace(content, 0) == 15


def test_find_matching_brace_handles_escape_in_string():
    content = '{ var s = "\\"}"; }'
    assert find_matching_brace(content, 0) == 17


def test_find_matching_brace_unmatched_returns_none():
    content = "{ if (x) {"
    assert find_matching_brace(content, 0) is None


def test_find_matching_brace_empty_body():
    content = "{}"
    assert find_matching_brace(content, 0) == 1


# ── find_expression_end ───────────────────────────────────────


def test_find_expression_end_simple():
    content = "x + 1;"
    assert find_expression_end(content, 0) == 5


def test_find_expression_end_with_parens():
    content = "Math.Max(a, b);"
    assert find_expression_end(content, 0) == 14


def test_find_expression_end_nested_parens():
    content = "foo(bar(x), baz(y; z));"
    assert find_expression_end(content, 0) == 22


def test_find_expression_end_with_brackets():
    content = "arr[i + 1];"
    assert find_expression_end(content, 0) == 10


def test_find_expression_end_with_curly():
    """Curly braces (e.g., collection initializers) delay semicolon matching."""
    content = "new List<int> { 1, 2, 3 };"
    assert find_expression_end(content, 0) == 25


def test_find_expression_end_skips_string():
    content = 'var s = "a;b";'
    assert find_expression_end(content, 0) == 13


def test_find_expression_end_no_semicolon():
    content = "x + 1"
    assert find_expression_end(content, 0) is None


def test_find_expression_end_from_offset():
    content = "skip; target;"
    assert find_expression_end(content, 6) == 12


# ── split_params ──────────────────────────────────────────────


def test_split_params_simple():
    assert split_params("int x, string y") == ["int x", " string y"]


def test_split_params_empty():
    assert split_params("") == []


def test_split_params_single():
    assert split_params("int x") == ["int x"]


def test_split_params_generic_type():
    """Commas inside generic brackets are not split points."""
    result = split_params("Dictionary<string, int> map, int count")
    assert len(result) == 2
    assert "Dictionary<string, int> map" in result[0]


def test_split_params_nested_generics():
    result = split_params("Func<int, List<string>> callback, bool flag")
    assert len(result) == 2


def test_split_params_with_tuple():
    result = split_params("(int, string) pair, int x")
    assert len(result) == 2


def test_split_params_with_array():
    result = split_params("int[] arr, string[,] matrix")
    assert len(result) == 2


# ── extract_csharp_params ─────────────────────────────────────


def test_extract_params_basic():
    names = extract_csharp_params("int x, string y")
    assert names == ["x", "y"]


def test_extract_params_empty():
    assert extract_csharp_params("") == []


def test_extract_params_strips_modifiers():
    names = extract_csharp_params("ref int x, out string y, in float z")
    assert names == ["x", "y", "z"]


def test_extract_params_strips_this():
    names = extract_csharp_params("this string s, int n")
    assert names == ["s", "n"]


def test_extract_params_strips_params_keyword():
    names = extract_csharp_params("params string[] args")
    assert names == ["args"]


def test_extract_params_strips_default_values():
    names = extract_csharp_params("int x = 0, string name = \"hello\"")
    assert names == ["x", "name"]


def test_extract_params_handles_at_prefix():
    """C# allows @-prefixed identifiers to use reserved words as names."""
    names = extract_csharp_params("int @class, string @event")
    assert names == ["class", "event"]


def test_extract_params_generic_type():
    names = extract_csharp_params("List<int> items, Dictionary<string, int> counts")
    assert names == ["items", "counts"]


def test_extract_params_ignores_non_identifier_tokens():
    """Tokens that aren't valid identifiers are skipped."""
    names = extract_csharp_params("int 123")
    assert names == []


def test_extract_params_with_required_modifier():
    names = extract_csharp_params("required string name")
    assert names == ["name"]


# ── extract_csharp_return_annotation ──────────────────────────


def test_return_annotation_basic():
    result = extract_csharp_return_annotation("public int MyMethod(", "MyMethod")
    assert result == "int"


def test_return_annotation_void():
    result = extract_csharp_return_annotation("public void Process(", "Process")
    assert result == "void"


def test_return_annotation_static():
    result = extract_csharp_return_annotation("public static string GetName(", "GetName")
    assert result == "string"


def test_return_annotation_generic():
    result = extract_csharp_return_annotation(
        "public List<int> GetItems(", "GetItems"
    )
    assert result == "List<int>"


def test_return_annotation_async():
    result = extract_csharp_return_annotation(
        "public async Task<bool> ValidateAsync(", "ValidateAsync"
    )
    assert result == "Task<bool>"


def test_return_annotation_no_match():
    result = extract_csharp_return_annotation("some random text", "NonExistent")
    assert result is None


def test_return_annotation_no_prefix():
    """If there's nothing before the method name, return None."""
    result = extract_csharp_return_annotation("MyMethod(", "MyMethod")
    assert result is None


def test_return_annotation_only_modifiers():
    """If prefix is all modifiers (no return type), return None."""
    result = extract_csharp_return_annotation("public static MyMethod(", "MyMethod")
    assert result is None


def test_return_annotation_override():
    result = extract_csharp_return_annotation(
        "protected override bool Equals(", "Equals"
    )
    assert result == "bool"


def test_return_annotation_multiple_occurrences_uses_last():
    """rfind ensures the last occurrence of 'Name(' is used."""
    result = extract_csharp_return_annotation(
        "int Name(int x) { } string Name(", "Name"
    )
    assert result == "string"
