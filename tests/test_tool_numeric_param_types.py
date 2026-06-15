"""Tests for numeric tool params sent as wrong types by the LLM.

LLMs sometimes send JSON like {"timeout": "60"} or {"max_results": "five"}
instead of integers. Previously these crashed with cryptic TypeErrors like
"'<' not supported between instances of 'str' and 'int'", which leak Python
internals to the LLM. Tools should coerce or reject such input cleanly.
"""

from src.tools import tool_bash, tool_glob, tool_list_files, tool_search


class TestBashTimeoutType:
    def test_timeout_as_numeric_string(self):
        """timeout='60' (string) should be coerced, not crash."""
        result = tool_bash(command="echo hi", timeout="60")
        assert "hi" in result
        assert "ERROR" not in result

    def test_timeout_as_invalid_string(self):
        """timeout='abc' can't be parsed — clear error, no traceback."""
        result = tool_bash(command="echo hi", timeout="abc")
        assert isinstance(result, str)
        assert "ERROR" in result or "exit code" not in result  # no crash
        # Must not leak the raw TypeError
        assert "not supported between" not in result

    def test_timeout_as_none(self):
        """timeout=None (omitted) should use the default."""
        result = tool_bash(command="echo hi", timeout=None)
        assert "hi" in result


class TestGlobMaxResultsType:
    def test_max_results_as_numeric_string(self):
        """max_results='5' should be coerced to int."""
        result = tool_glob(pattern="*.md", path=".", max_results="5")
        assert isinstance(result, str)
        assert "[ERROR]" not in result or "Path not found" in result

    def test_max_results_as_invalid_string(self):
        """max_results='lots' can't be parsed — no crash."""
        result = tool_glob(pattern="*.md", path=".", max_results="lots")
        assert isinstance(result, str)
        assert "not supported between" not in result


class TestListFilesMaxDepthType:
    def test_max_depth_as_numeric_string(self):
        """max_depth='2' should be coerced to int."""
        result = tool_list_files(path=".", max_depth="2")
        assert isinstance(result, str)
        assert "not supported between" not in result

    def test_max_depth_as_invalid_string(self):
        """max_depth='all' can't be parsed — no crash."""
        result = tool_list_files(path=".", max_depth="all")
        assert isinstance(result, str)
        assert "not supported between" not in result


class TestSearchNumericTypes:
    def test_max_results_numeric_string(self):
        """search max_results as numeric string should coerce."""
        result = tool_search(pattern="def", path="src", max_results="3")
        assert isinstance(result, str)
        assert "not supported between" not in result

    def test_context_numeric_string(self):
        """search context as numeric string should coerce."""
        result = tool_search(pattern="def", path="src", context="2", max_results=1)
        assert isinstance(result, str)
        assert "not supported between" not in result
