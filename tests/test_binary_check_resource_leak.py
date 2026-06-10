"""Tests for proper file handle closure in binary file detection.

The _cat, _head, and _tail commands check for binary files by opening
and reading the first 8KB. These tests verify that file handles are
properly closed after the check (regression test for resource leak).
"""

import os
import tempfile
import pytest

from src.repl import _run_cat_command, _run_head_command, _run_tail_command


@pytest.fixture
def tmpdir():
    with tempfile.TemporaryDirectory() as d:
        yield d


def _count_open_fds():
    """Count the number of open file descriptors for the current process."""
    try:
        return len(os.listdir(f"/proc/{os.getpid()}/fd"))
    except OSError:
        # macOS doesn't have /proc — skip FD counting
        pytest.skip("Cannot count FDs on this platform")


class TestBinaryCheckResourceLeak:
    """Verify that binary file checks don't leak file descriptors."""

    def test_cat_binary_check_no_leak(self, tmpdir):
        """_cat binary check should not leak file handles."""
        f = os.path.join(tmpdir, "test.txt")
        with open(f, "w") as fh:
            fh.write("hello world\n" * 100)

        baseline = _count_open_fds()
        # Call _cat many times to amplify any leak
        for _ in range(50):
            _run_cat_command(f)
        after = _count_open_fds()

        # Allow a small margin (±2) for unrelated FD changes
        assert abs(after - baseline) <= 2, (
            f"FD leak detected: baseline={baseline}, after={after}"
        )

    def test_head_binary_check_no_leak(self, tmpdir):
        """_head binary check should not leak file handles."""
        f = os.path.join(tmpdir, "test.txt")
        with open(f, "w") as fh:
            fh.write("hello world\n" * 100)

        baseline = _count_open_fds()
        for _ in range(50):
            _run_head_command(f)
        after = _count_open_fds()

        assert abs(after - baseline) <= 2, (
            f"FD leak detected: baseline={baseline}, after={after}"
        )

    def test_tail_binary_check_no_leak(self, tmpdir):
        """_tail binary check should not leak file handles."""
        f = os.path.join(tmpdir, "test.txt")
        with open(f, "w") as fh:
            fh.write("hello world\n" * 100)

        baseline = _count_open_fds()
        for _ in range(50):
            _run_tail_command(f)
        after = _count_open_fds()

        assert abs(after - baseline) <= 2, (
            f"FD leak detected: baseline={baseline}, after={after}"
        )


class TestBinaryFileDetection:
    """Verify binary file detection still works correctly."""

    def test_cat_rejects_binary(self, tmpdir):
        f = os.path.join(tmpdir, "binary.bin")
        with open(f, "wb") as fh:
            fh.write(b"hello\x00world")

        result = _run_cat_command(f)
        assert "Binary file" in result

    def test_head_rejects_binary(self, tmpdir):
        f = os.path.join(tmpdir, "binary.bin")
        with open(f, "wb") as fh:
            fh.write(b"hello\x00world\n" * 100)

        result = _run_head_command(f)
        assert "Binary file" in result

    def test_tail_rejects_binary(self, tmpdir):
        f = os.path.join(tmpdir, "binary.bin")
        with open(f, "wb") as fh:
            fh.write(b"hello\x00world\n" * 100)

        result = _run_tail_command(f)
        assert "Binary file" in result

    def test_cat_reads_text(self, tmpdir):
        f = os.path.join(tmpdir, "text.txt")
        with open(f, "w") as fh:
            fh.write("hello world\n")

        result = _run_cat_command(f)
        assert "hello world" in result
        assert "Binary file" not in result
