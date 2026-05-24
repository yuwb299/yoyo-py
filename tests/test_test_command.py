"""Tests for /test command."""

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.repl import _run_test_command


def _mock_completed_process(returncode=0, stdout="", stderr=""):
    """Create a mock CompletedProcess."""
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


class TestRunTestCommand:
    """Tests for the _run_test_command function."""

    @patch("src.repl.subprocess.run")
    def test_python_project_pytest_pass(self, mock_run):
        """Detect Python project and run pytest — passing."""
        with patch.object(Path, "exists", return_value=True):
            mock_run.return_value = _mock_completed_process(
                returncode=0, stdout="3 passed in 1.2s"
            )
            result = _run_test_command()
            assert "pass" in result.lower() or "✓" in result

    @patch("src.repl.subprocess.run")
    def test_python_project_pytest_fail(self, mock_run):
        """Detect Python project and report pytest failures."""
        with patch.object(Path, "exists", return_value=True):
            mock_run.return_value = _mock_completed_process(
                returncode=1, stdout="1 failed, 2 passed"
            )
            result = _run_test_command()
            assert "fail" in result.lower() or "✗" in result

    @patch("src.repl.subprocess.run")
    def test_pytest_not_installed(self, mock_run):
        """Handle pytest not being installed."""
        with patch.object(Path, "exists", return_value=True):
            mock_run.side_effect = FileNotFoundError("pytest not found")
            result = _run_test_command()
            assert "not installed" in result.lower() or "pip install" in result.lower()

    @patch("src.repl.subprocess.run")
    def test_timeout(self, mock_run):
        """Handle test timeout."""
        with patch.object(Path, "exists", return_value=True):
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="pytest", timeout=120)
            result = _run_test_command()
            # Strip ANSI codes for assertion
            clean = result.replace("\x1b[31m", "").replace("\x1b[0m", "")
            assert "timed out" in clean.lower()

    def test_no_project_detected(self):
        """Report error when no project type detected."""
        # Use a temp dir with no project files
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_test_command(workdir=tmpdir)
            assert "no recognized" in result.lower() or "can't determine" in result.lower()

    def test_invalid_directory(self):
        """Handle non-existent directory."""
        result = _run_test_command(workdir="/nonexistent/path/that/does/not/exist")
        assert "not found" in result.lower() or "error" in result.lower()
