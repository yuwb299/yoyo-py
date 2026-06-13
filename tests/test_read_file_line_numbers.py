"""Tests for correct line numbering in tool_read_file.

Regression: line numbers were off by one (line 1 displayed as 2, etc.)
because enumerate(start=start+1) already gave 1-indexed values, then
the f-string added i+1 again. This is silent data corruption — the
LLM relies on these numbers to know which lines to edit.
"""

import os
import tempfile

import pytest

from src.tools import tool_read_file


@pytest.fixture
def tmpdir():
    with tempfile.TemporaryDirectory() as d:
        yield d


class TestReadFileLineNumbers:
    """Verify per-line number prefixes match actual line positions."""

    def test_default_line_numbers(self, tmpdir):
        """First line should be numbered 1, not 2."""
        f = os.path.join(tmpdir, "a.txt")
        with open(f, "w") as fh:
            fh.write("alpha\nbeta\ngamma\n")

        result = tool_read_file(f)
        # line 1 must contain "alpha" with prefix "1" (right-aligned to 6)
        assert "     1|alpha" in result
        assert "     2|beta" in result
        assert "     3|gamma" in result
        # Must NOT show the off-by-one numbers
        assert "     2|alpha" not in result
        assert "     3|beta" not in result

    def test_line_numbers_with_offset(self, tmpdir):
        """Offset=2 should label the second line as 2."""
        f = os.path.join(tmpdir, "b.txt")
        with open(f, "w") as fh:
            fh.write("first\nsecond\nthird\nfourth\n")

        result = tool_read_file(f, offset=2, limit=2)
        assert "     2|second" in result
        assert "     3|third" in result
        assert "[Showing lines 2-3 of 4]" in result
        # No off-by-one
        assert "     3|second" not in result
        assert "     4|third" not in result

    def test_large_file_line_numbers(self, tmpdir):
        """Large-file incremental path must also number correctly."""
        f = os.path.join(tmpdir, "big.txt")
        # Write >512KB so the incremental path is used, with a small limit
        with open(f, "w") as fh:
            for i in range(1, 60001):  # 60K lines
                fh.write(f"line {i}\n")

        # offset=1, limit=3 → small range triggers incremental reading
        result = tool_read_file(f, offset=1, limit=3)
        assert "     1|line 1" in result
        assert "     2|line 2" in result
        assert "     3|line 3" in result
        # Off-by-one check
        assert "     2|line 1" not in result

    def test_large_file_offset_line_numbers(self, tmpdir):
        """Incremental path with a non-1 offset numbers correctly."""
        f = os.path.join(tmpdir, "big2.txt")
        with open(f, "w") as fh:
            for i in range(1, 60001):
                fh.write(f"line {i}\n")

        result = tool_read_file(f, offset=5000, limit=2)
        assert "  5000|line 5000" in result
        assert "  5001|line 5001" in result
        assert "[Showing lines 5000-5001 of 60000]" in result
        # Off-by-one
        assert "  5001|line 5000" not in result
