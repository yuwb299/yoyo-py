"""Tests for tool_search path validation.

Day 67: tool_search raised an UNCAUGHT TypeError when `path` was a non-string
(int/None/list). Unlike every other tool, the Path(path) call lived outside the
try/except block. The agent loop's generic handler caught it, but the resulting
"[ERROR] Error executing tool_search: expected str, bytes or os.PathLike object"
gives the LLM no way to know which argument was wrong. Now `path` is coerced via
_to_str with a param-named message, and empty path falls back to '.' instead of
leaking rg's "IO error for operation on : No such file" message.
"""

from src.tools import tool_search


class TestSearchPathNonString:
    """Non-string path values must produce a clear [ERROR], not a crash."""

    def test_int_path_returns_error_not_raise(self):
        # Previously: raised TypeError, caught by agent loop as cryptic message.
        # Now: returns a clear [ERROR] naming `path`.
        result = tool_search("def", path=123)
        assert result.startswith("[ERROR]")
        assert "path" in result.lower()
        assert "123" in result or "int" in result.lower()

    def test_list_path_returns_error_not_raise(self):
        # LLMs sometimes send paths as JSON arrays
        result = tool_search("def", path=["src"])
        assert result.startswith("[ERROR]")
        assert "path" in result.lower()

    def test_none_path_returns_error_not_raise(self):
        # None is falsy so the `if path:` check skips Path() — but then rg
        # gets None and crashes differently. After fix, None should be a
        # clear error OR treated as default. We accept either, just not a crash.
        result = tool_search("def", path=None)
        # Must not raise. Must be a string (either a valid result or [ERROR]).
        assert isinstance(result, str)

    def test_empty_string_path_treated_as_dot(self):
        """Empty string path should default to '.', not leak rg's IO error.

        Previously returned:
          '[WARN] Search encountered issues: rg: : IO error for operation
           on : No such file or directory (os error 2)'
        which is confusing and unactionable.
        """
        result = tool_search("def", path="")
        # Should NOT contain the raw rg IO error leak
        assert "IO error for operation on :" not in result


class TestSearchPathExistingBehavior:
    """Ensure the existing not-found check still works after adding coercion."""

    def test_nonexistent_path_returns_not_found(self, tmp_path):
        missing = tmp_path / "does_not_exist"
        result = tool_search("def", path=str(missing))
        assert result.startswith("[ERROR]")
        assert "not found" in result.lower()

    def test_valid_path_still_searches(self, tmp_path):
        # Create a file and search it
        f = tmp_path / "sample.py"
        f.write_text("def hello():\n    pass\n")
        result = tool_search("hello", path=str(tmp_path))
        assert "hello" in result
