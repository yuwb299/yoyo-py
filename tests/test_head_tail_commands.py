"""Tests for /head and /tail commands — efficient file preview."""

import os
import tempfile

from src.repl import _run_head_command, _run_tail_command


def _write_temp(content: str) -> str:
    """Write content to a temp file and return its path."""
    fd, path = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w") as f:
        f.write(content)
    return path


class TestHeadCommand:
    def test_basic_head(self):
        """Show first N lines of a file."""
        path = _write_temp("\n".join(f"line {i}" for i in range(1, 21)))
        try:
            result = _run_head_command(path)
            assert "line 1" in result
            assert "line 10" in result
            assert "line 11" not in result  # default 10 lines
            assert "first 10" in result
        finally:
            os.unlink(path)

    def test_head_with_count(self):
        """Show first N lines with explicit count."""
        path = _write_temp("\n".join(f"line {i}" for i in range(1, 21)))
        try:
            result = _run_head_command(f"{path} 5")
            assert "line 1" in result
            assert "line 5" in result
            assert "line 6" not in result
        finally:
            os.unlink(path)

    def test_head_file_shorter_than_count(self):
        """If file has fewer lines than requested, show all."""
        path = _write_temp("only line\n")
        try:
            result = _run_head_command(f"{path} 50")
            assert "only line" in result
        finally:
            os.unlink(path)

    def test_head_no_args(self):
        """No arguments shows usage."""
        result = _run_head_command("")
        assert "Usage" in result

    def test_head_nonexistent_file(self):
        """Non-existent file shows error."""
        result = _run_head_command("/tmp/nonexistent_file_xyz.txt")
        assert "not found" in result or "Error" in result

    def test_head_shows_line_numbers(self):
        """Output includes line numbers."""
        path = _write_temp("aaa\nbbb\nccc\n")
        try:
            result = _run_head_command(f"{path} 3")
            assert "1" in result
            assert "2" in result
            assert "3" in result
            assert "aaa" in result
        finally:
            os.unlink(path)

    def test_head_binary_file(self):
        """Binary files should be rejected."""
        fd, path = tempfile.mkstemp(suffix=".bin")
        with os.fdopen(fd, "wb") as f:
            f.write(b"\x00\x01\x02\x03")
        try:
            result = _run_head_command(path)
            assert "Binary" in result or "binary" in result
        finally:
            os.unlink(path)


class TestTailCommand:
    def test_basic_tail(self):
        """Show last N lines of a file."""
        path = _write_temp("\n".join(f"line {i}" for i in range(1, 21)))
        try:
            result = _run_tail_command(path)
            assert "line 11" in result
            assert "line 20" in result
            assert "line 10" not in result  # default 10 lines
        finally:
            os.unlink(path)

    def test_tail_with_count(self):
        """Show last N lines with explicit count."""
        path = _write_temp("\n".join(f"line {i}" for i in range(1, 21)))
        try:
            result = _run_tail_command(f"{path} 5")
            assert "line 16" in result
            assert "line 20" in result
            assert "line 15" not in result
        finally:
            os.unlink(path)

    def test_tail_file_shorter_than_count(self):
        """If file has fewer lines than requested, show all."""
        path = _write_temp("only line\n")
        try:
            result = _run_tail_command(f"{path} 50")
            assert "only line" in result
        finally:
            os.unlink(path)

    def test_tail_no_args(self):
        """No arguments shows usage."""
        result = _run_tail_command("")
        assert "Usage" in result

    def test_tail_nonexistent_file(self):
        """Non-existent file shows error."""
        result = _run_tail_command("/tmp/nonexistent_file_xyz.txt")
        assert "not found" in result or "Error" in result

    def test_tail_shows_line_numbers(self):
        """Output includes original line numbers (not relative)."""
        path = _write_temp("\n".join(f"line {i}" for i in range(1, 6)))
        try:
            result = _run_tail_command(f"{path} 2")
            # Lines 4 and 5 should be shown with original line numbers
            assert "4" in result
            assert "5" in result
            assert "line 4" in result
            assert "line 5" in result
        finally:
            os.unlink(path)

    def test_tail_binary_file(self):
        """Binary files should be rejected."""
        fd, path = tempfile.mkstemp(suffix=".bin")
        with os.fdopen(fd, "wb") as f:
            f.write(b"\x00\x01\x02\x03")
        try:
            result = _run_tail_command(path)
            assert "Binary" in result or "binary" in result
        finally:
            os.unlink(path)
