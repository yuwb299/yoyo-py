"""Tests for tool output preview in REPL display."""

import pytest
from unittest.mock import patch

from src.repl import _format_tool_output_preview


class TestFormatToolOutputPreview:
    """Test the tool output preview formatter."""

    def test_short_output_shown_in_full(self):
        result = _format_tool_output_preview("hello world")
        assert result == "hello world"

    def test_long_output_truncated(self):
        long_output = "x" * 500
        result = _format_tool_output_preview(long_output, max_len=200)
        assert len(result) < 300  # Allow room for truncation message
        assert "…" in result
        assert "500 chars" in result

    def test_empty_output(self):
        result = _format_tool_output_preview("")
        assert result == ""

    def test_none_output(self):
        result = _format_tool_output_preview(None)
        assert result == ""

    def test_multiline_output_truncated_to_first_lines(self):
        output = "line1\nline2\nline3\nline4\nline5\nline6\nline7\nline8"
        result = _format_tool_output_preview(output, max_lines=3, max_len=500)
        lines = result.split("\n")
        # Should show at most 3 lines plus truncation indicator
        assert len(lines) <= 4  # 3 lines + possible truncation

    def test_short_multiline_not_truncated(self):
        output = "line1\nline2\nline3"
        result = _format_tool_output_preview(output, max_lines=5, max_len=500)
        assert result == output

    def test_custom_max_len(self):
        output = "a" * 100
        result = _format_tool_output_preview(output, max_len=50)
        assert len(result) < 70
        assert "100 chars" in result

    def test_error_output_shown_with_prefix(self):
        result = _format_tool_output_preview("[ERROR] something failed", is_error=True)
        assert "something failed" in result

    def test_single_long_line_truncated(self):
        output = "a" * 1000
        result = _format_tool_output_preview(output, max_len=100)
        assert len(result) < 130
        assert "…" in result
