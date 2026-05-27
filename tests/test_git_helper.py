"""Tests for the shared _run_git helper function."""

import os
import subprocess
from unittest.mock import MagicMock, patch

from src.repl import _run_git


class TestRunGitHelper:
    """Test the module-level _run_git helper."""

    def test_basic_invocation(self):
        """_run_git should call subprocess.run with git + args."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "main\n"

        with patch("src.repl.subprocess.run", return_value=mock_result) as mock_run:
            result = _run_git("branch", "--show-current")

            mock_run.assert_called_once()
            call_args = mock_run.call_args
            assert call_args[0][0] == ["git", "branch", "--show-current"]
            assert call_args[1]["capture_output"] is True
            assert call_args[1]["text"] is True
            assert result.returncode == 0
            assert result.stdout == "main\n"

    def test_default_timeout(self):
        """_run_git should default to 10s timeout."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""

        with patch("src.repl.subprocess.run", return_value=mock_result) as mock_run:
            _run_git("status")

            call_args = mock_run.call_args
            assert call_args[1]["timeout"] == 10

    def test_custom_timeout(self):
        """_run_git should accept a custom timeout."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""

        with patch("src.repl.subprocess.run", return_value=mock_result) as mock_run:
            _run_git("status", timeout=5)

            call_args = mock_run.call_args
            assert call_args[1]["timeout"] == 5

    def test_custom_workdir(self):
        """_run_git should accept a custom working directory."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""

        with patch("src.repl.subprocess.run", return_value=mock_result) as mock_run:
            _run_git("status", workdir="/tmp")

            call_args = mock_run.call_args
            assert call_args[1]["cwd"] == "/tmp"

    def test_default_workdir_is_none(self):
        """_run_git without workdir should not pass cwd (uses os.getcwd())."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""

        with patch("src.repl.subprocess.run", return_value=mock_result) as mock_run:
            _run_git("status")

            call_args = mock_run.call_args
            assert "cwd" not in call_args[1] or call_args[1].get("cwd") is None

    def test_returns_completed_process(self):
        """_run_git should return the subprocess.CompletedProcess."""
        mock_result = subprocess.CompletedProcess(
            args=["git", "status"],
            returncode=0,
            stdout="On branch main\n",
            stderr="",
        )

        with patch("src.repl.subprocess.run", return_value=mock_result):
            result = _run_git("status")
            assert isinstance(result, subprocess.CompletedProcess)
            assert result.returncode == 0
            assert "main" in result.stdout
