"""Tests for boolean parameter coercion in tools.

LLMs sometimes send boolean params as JSON strings ("false", "true") or
as 0/1 ints. Without coercion, Python treats the string "false" as truthy,
causing silent data corruption (e.g. edit_file replaces ALL occurrences
instead of one). _to_bool handles this.
"""

import os
import tempfile
from pathlib import Path

from src.tools import _to_bool, tool_edit_file, tool_mkdir, tool_glob


# ── _to_bool unit tests ────────────────────────────────────────────────


class TestToBool:
    def test_actual_bool_passes_through(self):
        assert _to_bool(True, "x") is True
        assert _to_bool(False, "x") is False

    def test_true_strings(self):
        assert _to_bool("true", "x") is True
        assert _to_bool("True", "x") is True
        assert _to_bool("TRUE", "x") is True
        assert _to_bool("1", "x") is True
        assert _to_bool("yes", "x") is True
        assert _to_bool(" Yes ", "x") is True

    def test_false_strings(self):
        assert _to_bool("false", "x") is False
        assert _to_bool("False", "x") is False
        assert _to_bool("FALSE", "x") is False
        assert _to_bool("0", "x") is False
        assert _to_bool("no", "x") is False
        assert _to_bool("", "x") is False
        assert _to_bool("  ", "x") is False

    def test_ints(self):
        assert _to_bool(1, "x") is True
        assert _to_bool(0, "x") is False

    def test_floats(self):
        assert _to_bool(1.0, "x") is True
        assert _to_bool(0.0, "x") is False

    def test_invalid_raises(self):
        import pytest
        with pytest.raises(ValueError, match="replace_all"):
            _to_bool("maybe", "replace_all")
        with pytest.raises(ValueError, match="x"):
            _to_bool(["list"], "x")
        with pytest.raises(ValueError, match="x"):
            _to_bool({"k": 1}, "x")


# ── edit_file replace_all coercion ─────────────────────────────────────


class TestEditFileBoolCoercion:
    def test_replace_all_false_rejects_non_unique(self, tmp_path):
        """With actual False, non-unique old_string should ERROR, not silently
        replace all. This is correct behavior we want to preserve."""
        f = tmp_path / "test.txt"
        f.write_text("dup bar dup bar")

        result = tool_edit_file(str(f), "dup", "X", replace_all=False)
        assert "[ERROR]" in result
        assert "found 2 times" in result
        # File unchanged — no silent corruption
        assert f.read_text() == "dup bar dup bar"

    def test_replace_all_string_false_rejects_non_unique(self, tmp_path):
        """The BUG: replace_all='false' (string) used to be truthy → replace ALL.
        Now _to_bool coerces it to False, so non-unique → error, not silent replace."""
        f = tmp_path / "test.txt"
        f.write_text("dup bar dup bar")

        result = tool_edit_file(str(f), "dup", "X", replace_all="false")
        assert "[ERROR]" in result
        assert "found 2 times" in result
        # File unchanged — NOT silently corrupted by replacing all
        assert f.read_text() == "dup bar dup bar"

    def test_replace_all_string_true_replaces_all(self, tmp_path):
        """String 'true' must be treated as boolean True — replace all."""
        f = tmp_path / "test.txt"
        f.write_text("foo bar foo bar foo")

        result = tool_edit_file(str(f), "foo", "FOO", replace_all="true")
        assert "[OK]" in result
        assert f.read_text() == "FOO bar FOO bar FOO"


# ── mkdir parents coercion ─────────────────────────────────────────────


class TestMkdirBoolCoercion:
    def test_parents_false_string_creates_only_leaf(self, tmp_path):
        """parents='false' should NOT create parent dirs — should fail."""
        nested = tmp_path / "a" / "b" / "c"
        # parents='false' → coerced to False → parent 'a/b' doesn't exist → error
        result = tool_mkdir(str(nested), parents="false")
        assert "[ERROR]" in result

    def test_parents_true_string_creates_all(self, tmp_path):
        """parents='true' should create parent dirs."""
        nested = tmp_path / "a" / "b" / "c"
        result = tool_mkdir(str(nested), parents="true")
        assert "[OK]" in result
        assert nested.exists()


# ── search file_glob coercion ──────────────────────────────────────────


class TestSearchFileGlobCoercion:
    def test_file_glob_int_returns_error(self, tmp_path):
        """LLM sends file_glob as int — should get a clear param-named error."""
        from src.tools import tool_search
        f = tmp_path / "test.py"
        f.write_text("hello world")

        result = tool_search("hello", path=str(tmp_path), file_glob=123)
        assert "[ERROR]" in result
        assert "file_glob" in result
