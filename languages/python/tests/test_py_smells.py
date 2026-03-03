"""Tests for languages.python.detectors.smells — Python code smell detection."""

import textwrap
from pathlib import Path

from languages.python.detectors import smells as smells_mod
from languages.python.detectors.smells import (
    detect_smells,
)

# ── Helpers ────────────────────────────────────────────────


def _write_py(tmp_path: Path, code: str, filename: str = "test_mod.py") -> Path:
    """Write a Python file and return the directory containing it."""
    f = tmp_path / filename
    f.write_text(textwrap.dedent(code))
    return tmp_path


def _smell_ids(entries: list[dict]) -> set[str]:
    """Extract the set of smell IDs from detect_smells output."""
    return {e["id"] for e in entries}


def _find_smell(entries: list[dict], smell_id: str) -> dict | None:
    """Find a specific smell entry by ID."""
    for e in entries:
        if e["id"] == smell_id:
            return e
    return None


# ── Regex-based smell tests ───────────────────────────────


class TestEvalExec:
    def test_eval_detected(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            result = eval("1 + 2")
        """,
        )
        entries, _ = detect_smells(path)
        assert "eval_exec" in _smell_ids(entries)

    def test_exec_detected(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            exec("print('hello')")
        """,
        )
        entries, _ = detect_smells(path)
        assert "eval_exec" in _smell_ids(entries)

    def test_method_eval_not_flagged(self, tmp_path):
        """obj.eval() should not be flagged (lookbehind prevents it)."""
        path = _write_py(
            tmp_path,
            """\
            model.eval()
        """,
        )
        entries, _ = detect_smells(path)
        assert "eval_exec" not in _smell_ids(entries)


class TestTodoFixme:
    def test_todo(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            # TODO: fix this later
            x = 1
        """,
        )
        entries, _ = detect_smells(path)
        assert "todo_fixme" in _smell_ids(entries)

    def test_fixme(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            # FIXME: broken
            x = 1
        """,
        )
        entries, _ = detect_smells(path)
        assert "todo_fixme" in _smell_ids(entries)


class TestHardcodedUrl:
    def test_hardcoded_url_detected(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            url = fetch("https://api.example.com/data")
        """,
        )
        entries, _ = detect_smells(path)
        assert "hardcoded_url" in _smell_ids(entries)

    def test_constant_url_suppressed(self, tmp_path):
        """UPPER_CASE = 'http://...' is suppressed."""
        path = _write_py(
            tmp_path,
            """\
            BASE_URL = "https://api.example.com"
        """,
        )
        entries, _ = detect_smells(path)
        assert "hardcoded_url" not in _smell_ids(entries)


class TestMagicNumber:
    def test_magic_number(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            if count >= 10000:
                pass
        """,
        )
        entries, _ = detect_smells(path)
        assert "magic_number" in _smell_ids(entries)


# ── Multi-line / AST-based smell tests ────────────────────


class TestEmptyExcept:
    def test_except_pass(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            try:
                risky()
            except:
                pass
        """,
        )
        entries, _ = detect_smells(path)
        assert "empty_except" in _smell_ids(entries)

    def test_except_with_handling_ok(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            try:
                risky()
            except Exception as e:
                raise RuntimeError("oops") from e
        """,
        )
        entries, _ = detect_smells(path)
        assert "empty_except" not in _smell_ids(entries)


class TestSwallowedError:
    def test_only_logging(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            try:
                risky()
            except Exception as e:
                logging.error(e)
        """,
        )
        entries, _ = detect_smells(path)
        assert "swallowed_error" in _smell_ids(entries)

    def test_reraise_not_flagged(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            try:
                risky()
            except Exception as e:
                logging.error(e)
                raise
        """,
        )
        entries, _ = detect_smells(path)
        assert "swallowed_error" not in _smell_ids(entries)


class TestMonsterFunction:
    def test_monster_detected(self, tmp_path):
        body = "\n".join(f"    x_{i} = {i}" for i in range(160))
        code = f"def monster():\n{body}\n"
        path = _write_py(tmp_path, code)
        entries, _ = detect_smells(path)
        assert "monster_function" in _smell_ids(entries)

    def test_small_function_ok(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            def small():
                return 42
        """,
        )
        entries, _ = detect_smells(path)
        assert "monster_function" not in _smell_ids(entries)


class TestDeadFunction:
    def test_pass_only(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            def noop():
                pass
        """,
        )
        entries, _ = detect_smells(path)
        assert "dead_function" in _smell_ids(entries)

    def test_return_none(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            def noop2():
                return None
        """,
        )
        entries, _ = detect_smells(path)
        assert "dead_function" in _smell_ids(entries)

    def test_real_function_not_flagged(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            def real():
                return 42
        """,
        )
        entries, _ = detect_smells(path)
        assert "dead_function" not in _smell_ids(entries)

    def test_decorated_function_not_flagged(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            @abstractmethod
            def interface():
                pass
        """,
        )
        entries, _ = detect_smells(path)
        assert "dead_function" not in _smell_ids(entries)


class TestDeferredImport:
    def test_import_inside_function(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            def lazy():
                import json
                return json.dumps({})
        """,
        )
        entries, _ = detect_smells(path)
        assert "deferred_import" in _smell_ids(entries)

    def test_typing_import_not_flagged(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            def typed():
                from typing import Optional
                return None
        """,
        )
        entries, _ = detect_smells(path)
        assert "deferred_import" not in _smell_ids(entries)


class TestInlineClass:
    def test_class_inside_function(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            def outer():
                class Inner:
                    pass
                return Inner()
        """,
        )
        entries, _ = detect_smells(path)
        assert "inline_class" in _smell_ids(entries)


class TestSubprocessNoTimeout:
    def test_subprocess_run_no_timeout(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            import subprocess
            def run_it():
                subprocess.run(["ls"])
        """,
        )
        entries, _ = detect_smells(path)
        assert "subprocess_no_timeout" in _smell_ids(entries)

    def test_subprocess_with_timeout_ok(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            import subprocess
            def run_it():
                subprocess.run(["ls"], timeout=30)
        """,
        )
        entries, _ = detect_smells(path)
        assert "subprocess_no_timeout" not in _smell_ids(entries)


class TestUnreachableCode:
    def test_code_after_return(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            def early():
                return 1
                x = 2
        """,
        )
        entries, _ = detect_smells(path)
        assert "unreachable_code" in _smell_ids(entries)

    def test_code_after_raise(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            def raiser():
                raise ValueError("bad")
                cleanup()
        """,
        )
        entries, _ = detect_smells(path)
        assert "unreachable_code" in _smell_ids(entries)


class TestConstantReturn:
    def test_always_returns_true(self, tmp_path):
        # Needs >=4 LOC, >=2 returns, conditional logic
        path = _write_py(
            tmp_path,
            """\
            def always_true(x):
                if x > 0:
                    return True
                elif x < 0:
                    return True
                else:
                    return True
        """,
        )
        entries, _ = detect_smells(path)
        assert "constant_return" in _smell_ids(entries)

    def test_varying_returns_ok(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            def varying(x):
                if x > 0:
                    return True
                else:
                    return False
        """,
        )
        entries, _ = detect_smells(path)
        assert "constant_return" not in _smell_ids(entries)


class TestRegexBacktrack:
    def test_nested_quantifiers(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            import re
            pat = re.compile(r"(a+)+b")
        """,
        )
        entries, _ = detect_smells(path)
        assert "regex_backtrack" in _smell_ids(entries)

    def test_safe_regex_ok(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            import re
            pat = re.compile(r"[a-z]+\\d+")
        """,
        )
        entries, _ = detect_smells(path)
        assert "regex_backtrack" not in _smell_ids(entries)


class TestNaiveCommentStrip:
    def test_re_sub_comment_strip(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            import re
            cleaned = re.sub(r"//[^\\n]*", "", text)
        """,
        )
        entries, _ = detect_smells(path)
        assert "naive_comment_strip" in _smell_ids(entries)


class TestUnsafeFileWrite:
    def test_write_text_no_atomic(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            from pathlib import Path
            def save(data):
                Path("out.txt").write_text(data)
        """,
        )
        entries, _ = detect_smells(path)
        assert "unsafe_file_write" in _smell_ids(entries)

    def test_write_with_os_replace_ok(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            import os
            from pathlib import Path
            def safe_save(data):
                Path("out.tmp").write_text(data)
                os.replace("out.tmp", "out.txt")
        """,
        )
        entries, _ = detect_smells(path)
        assert "unsafe_file_write" not in _smell_ids(entries)


# ── Multi-line string filtering ───────────────────────────


class TestBuildStringLineSet:
    def test_triple_quote_lines_excluded(self):
        lines = [
            'x = """',
            'eval("danger")',
            '"""',
            'eval("real")',
        ]
        string_lines = smells_mod._build_string_line_set(lines)
        assert 1 in string_lines  # inside triple-quote
        assert 3 not in string_lines  # outside triple-quote

    def test_same_line_triple_quote(self):
        lines = ['x = """hello"""', 'eval("real")']
        string_lines = smells_mod._build_string_line_set(lines)
        assert 0 not in string_lines  # closed on same line
        assert 1 not in string_lines


class TestMatchIsInString:
    def test_match_outside_string(self):
        assert not smells_mod._match_is_in_string('eval("code")', 0)

    def test_match_inside_string(self):
        line = '"eval(x)" + stuff'
        idx = line.index("eval")
        assert smells_mod._match_is_in_string(line, idx)

    def test_match_in_comment(self):
        line = "x = 1  # eval(x)"
        idx = line.index("eval")
        assert smells_mod._match_is_in_string(line, idx)


# ── Clean code produces no high-severity smells ───────────


class TestCleanCode:
    def test_clean_file(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            \"\"\"A clean module.\"\"\"

            import os
            from pathlib import Path


            def greet(name: str) -> str:
                return f"Hello, {name}"


            class Config:
                DEBUG = False
                VERSION = "1.0"
        """,
        )
        entries, count = detect_smells(path)
        high = [e for e in entries if e["severity"] == "high"]
        assert len(high) == 0
        assert count == 1


# ── Duplicate constants (cross-file) ─────────────────────


class TestDuplicateConstants:
    def test_same_constant_in_two_files(self, tmp_path):
        (tmp_path / "a.py").write_text("MAX_RETRIES = 3\n")
        (tmp_path / "b.py").write_text("MAX_RETRIES = 3\n")
        entries, _ = detect_smells(tmp_path)
        assert "duplicate_constant" in _smell_ids(entries)

    def test_different_constants_ok(self, tmp_path):
        (tmp_path / "a.py").write_text("MAX_RETRIES = 3\n")
        (tmp_path / "b.py").write_text("MAX_RETRIES = 5\n")
        entries, _ = detect_smells(tmp_path)
        assert "duplicate_constant" not in _smell_ids(entries)


# ── star_import_no_all ────────────────────────────────────


class TestStarImportNoAll:
    def test_star_import_target_without_all(self, tmp_path):
        """from .helper import * where helper.py has no __all__ -> flagged."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "helper.py").write_text("def foo(): pass\n")
        (pkg / "main.py").write_text("from .helper import *\n")
        entries, _ = detect_smells(pkg)
        assert "star_import_no_all" in _smell_ids(entries)

    def test_star_import_target_with_all(self, tmp_path):
        """from .helper import * where helper.py defines __all__ -> not flagged."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "helper.py").write_text('__all__ = ["foo"]\ndef foo(): pass\n')
        (pkg / "main.py").write_text("from .helper import *\n")
        entries, _ = detect_smells(pkg)
        assert "star_import_no_all" not in _smell_ids(entries)

    def test_absolute_star_import_target_without_all_from_scan_root(self, tmp_path):
        """from mypkg.helper import * resolves when scanning the project root."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "helper.py").write_text("def foo(): pass\n")
        (tmp_path / "main.py").write_text("from mypkg.helper import *\n")

        entries, _ = detect_smells(tmp_path)

        assert "star_import_no_all" in _smell_ids(entries)

    def test_absolute_star_import_target_without_all_from_package_scan(self, tmp_path):
        """from mypkg.helper import * resolves when scanning a single package."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "helper.py").write_text("def foo(): pass\n")
        (pkg / "main.py").write_text("from mypkg.helper import *\n")

        entries, _ = detect_smells(pkg)

        assert "star_import_no_all" in _smell_ids(entries)


# ── Output structure ──────────────────────────────────────


class TestOutputStructure:
    def test_entry_keys(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            def foo(items=[]):
                pass
        """,
        )
        entries, _ = detect_smells(path)
        assert len(entries) > 0
        e = entries[0]
        assert "id" in e
        assert "label" in e
        assert "severity" in e
        assert "count" in e
        assert "files" in e
        assert "matches" in e

    def test_severity_sort_order(self, tmp_path):
        """Entries should be sorted high -> medium -> low."""
        path = _write_py(
            tmp_path,
            """\
            # TODO: something
            def foo(items=[]):
                pass
        """,
        )
        entries, _ = detect_smells(path)
        severities = [e["severity"] for e in entries]
        order = {"high": 0, "medium": 1, "low": 2}
        ranks = [order[s] for s in severities]
        assert ranks == sorted(ranks)


# ── #48: lost_exception_context ───────────────────────────


# ── #49: vestigial_parameter ──────────────────────────────


class TestVestigialParameter:
    def test_unused_comment_detected(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            def process(
                data,
                legacy_mode=False,  # unused, kept for backward compat
            ):
                return data
        """,
        )
        entries, _ = detect_smells(path)
        assert "vestigial_parameter" in _smell_ids(entries)

    def test_deprecated_comment_detected(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            def fetch(url, timeout=30):  # deprecated, no longer used
                return url
        """,
        )
        entries, _ = detect_smells(path)
        assert "vestigial_parameter" in _smell_ids(entries)

    def test_normal_comment_ok(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            def fetch(url, timeout=30):  # seconds
                return url
        """,
        )
        entries, _ = detect_smells(path)
        assert "vestigial_parameter" not in _smell_ids(entries)


# ── #49: noop_function ────────────────────────────────────


class TestNoopFunction:
    def test_noop_detected(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            def process(data):
                if not data:
                    return
                logger.info("processing")
                print("done")
                return
        """,
        )
        entries, _ = detect_smells(path)
        assert "noop_function" in _smell_ids(entries)

    def test_real_function_ok(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            def process(data):
                result = transform(data)
                save(result)
                return result
        """,
        )
        entries, _ = detect_smells(path)
        assert "noop_function" not in _smell_ids(entries)

    def test_short_function_not_flagged(self, tmp_path):
        """Functions with < 3 statements (after docstring) are too short to flag."""
        path = _write_py(
            tmp_path,
            """\
            def stub():
                pass
                return
        """,
        )
        entries, _ = detect_smells(path)
        assert "noop_function" not in _smell_ids(entries)

    def test_init_not_flagged(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            class Foo:
                def __init__(self):
                    pass
                    return
                    return
        """,
        )
        entries, _ = detect_smells(path)
        assert "noop_function" not in _smell_ids(entries)

    def test_decorated_not_flagged(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            @abstractmethod
            def interface(self):
                pass
                return
                return
        """,
        )
        entries, _ = detect_smells(path)
        assert "noop_function" not in _smell_ids(entries)


# ── #49: stderr_traceback ─────────────────────────────────


class TestStderrTraceback:
    def test_print_exc_detected(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            import traceback
            try:
                risky()
            except Exception:
                traceback.print_exc()
        """,
        )
        entries, _ = detect_smells(path)
        assert "stderr_traceback" in _smell_ids(entries)

    def test_no_traceback_ok(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            import logging
            try:
                risky()
            except Exception:
                logging.exception("failed")
        """,
        )
        entries, _ = detect_smells(path)
        assert "stderr_traceback" not in _smell_ids(entries)


class TestBoundaryPurity:
    def test_import_time_boundary_mutations_detected(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            import sys
            import logging
            from dotenv import load_dotenv

            sys.path.append("/tmp/local")
            load_dotenv()
            logging.basicConfig(level=logging.INFO)
        """,
        )
        entries, _ = detect_smells(path)
        ids = _smell_ids(entries)
        assert "import_path_mutation" in ids
        assert "import_env_mutation" in ids
        assert "import_runtime_init" in ids

    def test_main_guard_suppresses_boundary_mutation_smells(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            import sys
            from dotenv import load_dotenv

            if __name__ == "__main__":
                sys.path.insert(0, "/tmp/local")
                load_dotenv()
        """,
        )
        entries, _ = detect_smells(path)
        ids = _smell_ids(entries)
        assert "import_path_mutation" not in ids
        assert "import_env_mutation" not in ids

    def test_function_scope_does_not_trigger_import_time_smell(self, tmp_path):
        path = _write_py(
            tmp_path,
            """\
            import sys

            def configure():
                sys.path.append("/tmp/local")
        """,
        )
        entries, _ = detect_smells(path)
        assert "import_path_mutation" not in _smell_ids(entries)
