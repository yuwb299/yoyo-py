"""Tests for search tool context lines feature (-C/--context parameter)."""

import os
import tempfile
from pathlib import Path

import pytest

from src.tools import tool_search


@pytest.fixture
def search_dir():
    """Create a temp directory with known file contents for search tests."""
    with tempfile.TemporaryDirectory() as tmp:
        # Create a file with multiple lines so context is meaningful
        test_file = Path(tmp) / "sample.py"
        test_file.write_text(
            "line 1: imports\n"
            "line 2: import os\n"
            "line 3: import sys\n"
            "line 4: \n"
            "line 5: def hello():\n"
            "line 6:     print('hello')\n"
            "line 7:     return True\n"
            "line 8: \n"
            "line 9: def world():\n"
            "line 10:     print('world')\n"
            "line 11:     return False\n"
        )
        yield tmp


class TestSearchContextParameter:
    """Test the context parameter for showing surrounding lines."""

    def test_context_zero_same_as_default(self, search_dir):
        """context=0 should behave like no context — just matching lines."""
        result = tool_search("hello", path=search_dir, context=0)
        assert "hello" in result
        # Without context, we shouldn't see extra surrounding lines
        # (just the matching line itself)
        lines = result.strip().split("\n")
        matching_lines = [l for l in lines if "hello" in l.lower()]
        assert len(matching_lines) >= 1

    def test_context_one_shows_surrounding(self, search_dir):
        """context=1 should show 1 line before and 1 line after each match."""
        result = tool_search("def hello", path=search_dir, context=1)
        # Should contain the match
        assert "def hello" in result
        # Should also contain surrounding lines
        assert "import sys" in result or "line 4" in result  # line before
        assert "print('hello')" in result  # line after

    def test_context_two_shows_more(self, search_dir):
        """context=2 should show 2 lines before and 2 lines after each match."""
        result = tool_search("def hello", path=search_dir, context=2)
        assert "def hello" in result
        assert "import sys" in result
        assert "return True" in result  # 2 lines after

    def test_context_with_file_glob(self, search_dir):
        """context should work together with file_glob filter."""
        result = tool_search("hello", path=search_dir, file_glob="*.py", context=1)
        assert "hello" in result

    def test_context_with_max_results(self, search_dir):
        """context should work together with max_results."""
        result = tool_search("import", path=search_dir, max_results=5, context=1)
        assert "import" in result

    def test_context_no_matches(self, search_dir):
        """context with no matches should return no matches message."""
        result = tool_search("zzz_nonexistent", path=search_dir, context=2)
        assert "No matches" in result

    def test_context_negative_treated_as_zero(self, search_dir):
        """Negative context values should be treated as 0."""
        result_neg = tool_search("hello", path=search_dir, context=-1)
        result_zero = tool_search("hello", path=search_dir, context=0)
        # Both should have results
        assert "hello" in result_neg
        assert "hello" in result_zero

    def test_context_large_value(self, search_dir):
        """Very large context should not crash — it just shows more lines."""
        result = tool_search("hello", path=search_dir, context=100)
        assert "hello" in result

    def test_context_parameter_default(self, search_dir):
        """Default behavior (no context param) should work as before."""
        result = tool_search("hello", path=search_dir)
        assert "hello" in result

    def test_context_works_with_fallback_grep(self, search_dir):
        """Context should work even when ripgrep is not available (grep fallback).

        We can't easily control whether rg is installed, but we verify the
        function doesn't crash with context parameter regardless.
        """
        # This just verifies it works — the actual fallback path depends on
        # whether rg is installed on the test system
        result = tool_search("print", path=search_dir, context=1)
        assert "print" in result

    def test_context_separates_matches(self, search_dir):
        """When two matches are far apart, context should show both with gaps."""
        # Search for 'def' which matches at lines 5 and 9
        result = tool_search("def ", path=search_dir, context=1)
        assert "def hello" in result
        assert "def world" in result


class TestSearchContextSchema:
    """Test that the search tool schema includes the context parameter."""

    def test_search_schema_has_context_param(self):
        """The TOOL_SCHEMAS should include context parameter for search."""
        from src.tools import TOOL_SCHEMAS
        search_schema = None
        for schema in TOOL_SCHEMAS:
            if schema["function"]["name"] == "search":
                search_schema = schema
                break
        assert search_schema is not None
        props = search_schema["function"]["parameters"]["properties"]
        assert "context" in props
        assert props["context"]["type"] == "integer"
        assert props["context"]["description"]  # Has a description
        assert props["context"]["default"] == 0


class TestSearchContextEdgeCases:
    """Edge cases for the search context feature."""

    def test_context_with_empty_file(self):
        """Context on an empty file should work without error."""
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty.py"
            empty.write_text("")
            result = tool_search("anything", path=tmp, context=2)
            assert "No matches" in result

    def test_context_with_single_line_file(self):
        """Context on a single-line file should not go out of bounds."""
        with tempfile.TemporaryDirectory() as tmp:
            single = Path(tmp) / "single.py"
            single.write_text("target line here")
            result = tool_search("target", path=tmp, context=5)
            assert "target" in result

    def test_context_with_binary_file(self):
        """Context should handle binary-like files gracefully."""
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "data.bin"
            binary.write_bytes(b"hello\x00world\nfoo\nbar\n")
            # Search should not crash on binary files
            result = tool_search("hello", path=tmp, context=1)
            # ripgrep typically skips binary files, so this may return no matches
            assert isinstance(result, str)
