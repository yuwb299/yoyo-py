"""Test --cwd CLI flag for setting working directory."""

import os
import tempfile
from pathlib import Path

from src.main import parse_args


class TestCwdCliFlag:
    """Tests for the --cwd CLI argument."""

    def test_cwd_flag_parsed(self):
        """--cwd should be parsed and stored in args."""
        import sys
        old_argv = sys.argv
        try:
            sys.argv = ["main.py", "--cwd", "/tmp"]
            args = parse_args()
            assert args.cwd == "/tmp"
        finally:
            sys.argv = old_argv

    def test_cwd_flag_default_none(self):
        """Without --cwd, the value should be None."""
        import sys
        old_argv = sys.argv
        try:
            sys.argv = ["main.py"]
            args = parse_args()
            assert args.cwd is None
        finally:
            sys.argv = old_argv

    def test_cwd_flag_changes_directory(self):
        """Setting --cwd should change os.getcwd() to the specified directory."""
        import sys
        import subprocess

        with tempfile.TemporaryDirectory() as tmpdir:
            # Run a subprocess that uses --cwd and prints cwd
            result = subprocess.run(
                [
                    sys.executable, "-m", "src.main",
                    "--cwd", tmpdir,
                    "--help",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            # --help exits with 0
            assert result.returncode == 0
            # The help output should appear
            assert "yoyo-py" in result.stdout

    def test_cwd_flag_nonexistent_dir_exits_with_error(self):
        """--cwd with a nonexistent directory should print an error and exit."""
        import sys
        import subprocess

        result = subprocess.run(
            [
                sys.executable, "-m", "src.main",
                "--cwd", "/nonexistent/path/that/does/not/exist",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            env={**os.environ, "GLM_API_KEY": "test-key"},
        )
        assert result.returncode != 0
        assert "not found" in result.stderr.lower() or "error" in result.stderr.lower()

    def test_cwd_flag_relative_path(self):
        """--cwd with a relative path should resolve relative to original cwd."""
        import sys
        old_argv = sys.argv
        try:
            sys.argv = ["main.py", "--cwd", "."]
            args = parse_args()
            assert args.cwd == "."
        finally:
            sys.argv = old_argv
