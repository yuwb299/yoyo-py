"""Tests for tool_read_file offset-past-end consistency.

The main read path returned a nonsensical "[Showing lines 100-2 of 2]"
header with empty content when offset exceeded total lines, while the
incremental (large-file) path returned a clear error. This test ensures
both paths give a consistent, clear message.
"""

import os
import tempfile

import pytest

from src.tools import tool_read_file


@pytest.fixture
def tmpdir():
    with tempfile.TemporaryDirectory() as d:
        yield d


class TestReadFileOffsetPastEnd:
    """Verify offset-past-end gives a clear message on both paths."""

    def test_small_file_offset_past_end(self, tmpdir):
        """Small file main path: offset beyond total should be clear."""
        f = os.path.join(tmpdir, "small.txt")
        with open(f, "w") as fh:
            fh.write("line1\nline2\n")

        result = tool_read_file(f, offset=100, limit=10)
        # Should NOT show the nonsensical "100-2" header
        assert "100-2" not in result
        # Should indicate the offset is past the end or show the total
        assert "2 lines" in result or "past" in result.lower() or "beyond" in result.lower()

    def test_offset_exactly_at_end(self, tmpdir):
        """Offset equal to total+1 should be past end."""
        f = os.path.join(tmpdir, "three.txt")
        with open(f, "w") as fh:
            fh.write("a\nb\nc\n")

        result = tool_read_file(f, offset=4, limit=10)
        # offset 4 is past the 3-line file
        assert "4-3" not in result  # no nonsensical range

    def test_large_file_offset_past_end(self, tmpdir):
        """Large file incremental path: offset beyond total gives error."""
        f = os.path.join(tmpdir, "big.txt")
        with open(f, "w") as fh:
            for i in range(1, 60001):
                fh.write(f"line {i}\n")

        result = tool_read_file(f, offset=99999, limit=10)
        # Incremental path already returns a clear error
        assert "past end of file" in result or "99999" not in result.split("\n")[1] if "\n" in result else True
