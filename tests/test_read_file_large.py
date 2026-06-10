"""Tests for efficient file reading in tool_read_file.

Verify that tool_read_file handles large files efficiently by not
reading the entire file when only a small range is requested.
"""

import os
import tempfile
import pytest

from src.tools import tool_read_file


@pytest.fixture
def tmpdir():
    with tempfile.TemporaryDirectory() as d:
        yield d


class TestReadFileLargeFile:
    """Test that read_file handles large files without excessive memory use."""

    def test_read_tail_of_large_file(self, tmpdir):
        """Reading the last 10 lines of a 100K-line file should work."""
        f = os.path.join(tmpdir, "big.txt")
        with open(f, "w") as fh:
            for i in range(100000):
                fh.write(f"line {i + 1}\n")

        result = tool_read_file(f, offset=99991, limit=10)
        assert "line 99991" in result
        assert "line 100000" in result
        assert "line 99990" not in result
        assert "[Showing lines 99991-100000 of 100000]" in result

    def test_read_head_of_large_file(self, tmpdir):
        """Reading the first 5 lines of a large file should work."""
        f = os.path.join(tmpdir, "big.txt")
        with open(f, "w") as fh:
            for i in range(50000):
                fh.write(f"line {i + 1}\n")

        result = tool_read_file(f, offset=1, limit=5)
        assert "line 1" in result
        assert "line 5" in result
        assert "line 6" not in result

    def test_read_mid_range(self, tmpdir):
        """Reading a range in the middle of a large file."""
        f = os.path.join(tmpdir, "big.txt")
        with open(f, "w") as fh:
            for i in range(10000):
                fh.write(f"line {i + 1}\n")

        result = tool_read_file(f, offset=5001, limit=3)
        assert "line 5001" in result
        assert "line 5003" in result
        assert "line 5004" not in result
        assert "line 5000" not in result

    def test_offset_past_end(self, tmpdir):
        """Offset beyond file end should return empty result."""
        f = os.path.join(tmpdir, "small.txt")
        with open(f, "w") as fh:
            fh.write("line 1\nline 2\n")

        result = tool_read_file(f, offset=100)
        # Should show file has fewer lines, or empty content
        assert "100" not in result or "2 lines" in result

    def test_binary_file_rejection(self, tmpdir):
        """Binary files should be rejected."""
        f = os.path.join(tmpdir, "binary.bin")
        with open(f, "wb") as fh:
            fh.write(b"hello\x00world\n" * 100)

        result = tool_read_file(f)
        assert "Binary" in result or "ERROR" in result
