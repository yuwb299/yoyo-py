"""Tests for /du command — show file and directory sizes."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from src.repl import _run_du_command


def _write_temp_file(directory: str, name: str, content: str) -> str:
    """Write a file in the given directory and return its path."""
    path = os.path.join(directory, name)
    with open(path, "w") as f:
        f.write(content)
    return path


class TestDuCommand:
    def test_file_size(self):
        """Show size of a specific file."""
        tmpdir = tempfile.mkdtemp()
        try:
            path = _write_temp_file(tmpdir, "test.txt", "x" * 1000)
            result = _run_du_command(path)
            assert "test.txt" in result
            assert "B" in result or "KB" in result or "byte" in result.lower()
        finally:
            import subprocess
            subprocess.run(["rm", "-rf", tmpdir], capture_output=True)

    def test_directory_size(self):
        """Show sizes of files in a directory."""
        tmpdir = tempfile.mkdtemp()
        try:
            _write_temp_file(tmpdir, "a.txt", "a" * 100)
            _write_temp_file(tmpdir, "b.txt", "b" * 200)
            # Mock subprocess.run for du -sk calls on subdirectories
            from subprocess import CompletedProcess
            with patch("src.repl.subprocess.run") as mock_run:
                mock_run.return_value = CompletedProcess(
                    args=[], returncode=0, stdout="0\t" + tmpdir, stderr=""
                )
                result = _run_du_command(tmpdir)
            assert "a.txt" in result
            assert "b.txt" in result
        finally:
            import subprocess
            subprocess.run(["rm", "-rf", tmpdir], capture_output=True)

    def test_no_args(self):
        """No args shows current directory."""
        result = _run_du_command("")
        assert result  # Should show something for current dir

    def test_nonexistent_path(self):
        """Non-existent path shows error."""
        result = _run_du_command("/tmp/nonexistent_xyz_123")
        assert "not found" in result.lower() or "error" in result.lower()

    def test_sorted_by_size(self):
        """Files should be sorted by size (largest first)."""
        tmpdir = tempfile.mkdtemp()
        try:
            _write_temp_file(tmpdir, "small.txt", "s")
            _write_temp_file(tmpdir, "large.txt", "x" * 10000)
            from subprocess import CompletedProcess
            with patch("src.repl.subprocess.run") as mock_run:
                mock_run.return_value = CompletedProcess(
                    args=[], returncode=0, stdout="0\t" + tmpdir, stderr=""
                )
                result = _run_du_command(tmpdir)
            # large.txt should appear before small.txt
            large_pos = result.find("large.txt")
            small_pos = result.find("small.txt")
            assert large_pos < small_pos, "Larger files should appear first"
        finally:
            import subprocess
            subprocess.run(["rm", "-rf", tmpdir], capture_output=True)

    def test_human_readable_sizes(self):
        """Sizes should be human-readable (KB, MB, etc.)."""
        tmpdir = tempfile.mkdtemp()
        try:
            _write_temp_file(tmpdir, "big.txt", "x" * 50000)
            from subprocess import CompletedProcess
            with patch("src.repl.subprocess.run") as mock_run:
                mock_run.return_value = CompletedProcess(
                    args=[], returncode=0, stdout="0\t" + tmpdir, stderr=""
                )
                result = _run_du_command(tmpdir)
            assert "KB" in result or "B" in result
        finally:
            import subprocess
            subprocess.run(["rm", "-rf", tmpdir], capture_output=True)
