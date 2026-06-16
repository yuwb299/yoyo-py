"""Tests for glob/search tools rejecting non-string pattern/path params.

LLMs sometimes send a numeric or null pattern. Previously:
- glob(pattern=42) crashed inside pathlib with "'int' object is not subscriptable"
  — totally unhelpful, leaks Python internals.
- search(pattern=None) returned the empty-pattern error (acceptable).
- search(pattern=42) leaked "expected str..." from ripgrep's path handling.

All should return a clear param-named [ERROR].
"""

from src.tools import tool_glob, tool_search


class TestGlobNonStringPattern:
    def test_int_pattern_clear_error(self, tmp_path):
        result = tool_glob(pattern=42, path=str(tmp_path))
        assert "[ERROR]" in result
        assert "pattern" in result.lower()
        # Must not leak the cryptic internals
        assert "not subscriptable" not in result

    def test_none_pattern_clear_error(self, tmp_path):
        result = tool_glob(pattern=None, path=str(tmp_path))
        assert "[ERROR]" in result
        assert "pattern" in result.lower()

    def test_list_pattern_clear_error(self, tmp_path):
        result = tool_glob(pattern=["*.py"], path=str(tmp_path))
        assert "[ERROR]" in result
        assert "pattern" in result.lower()

    def test_string_pattern_still_works(self, tmp_path):
        (tmp_path / "a.py").write_text("x")
        result = tool_glob(pattern="*.py", path=str(tmp_path))
        assert "[OK]" in result or "a.py" in result


class TestSearchNonStringPattern:
    def test_int_pattern_clear_error(self, tmp_path):
        result = tool_search(pattern=42, path=str(tmp_path))
        assert "[ERROR]" in result
        assert "pattern" in result.lower()

    def test_none_pattern_clear_error(self, tmp_path):
        # None should be treated as empty → clear empty-pattern message
        result = tool_search(pattern=None, path=str(tmp_path))
        assert "[ERROR]" in result

    def test_list_pattern_clear_error(self, tmp_path):
        result = tool_search(pattern=["foo"], path=str(tmp_path))
        assert "[ERROR]" in result
        assert "pattern" in result.lower()
