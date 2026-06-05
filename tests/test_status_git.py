"""Tests for git info in /status command."""

import os
import subprocess
import pytest
from unittest.mock import patch, MagicMock

from src.repl import _git_status_line, _format_status_output


class TestGitStatusLine:
    """Tests for _git_status_line helper."""

    def test_returns_none_outside_git_repo(self):
        """Returns None when not in a git repo."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=128, stdout="", stderr="fatal: not a git repo")
            result = _git_status_line()
        assert result is None

    def test_returns_branch_in_git_repo(self):
        """Returns branch name in a git repo."""
        with patch("subprocess.run") as mock_run:
            # First call: git symbolic-ref --short HEAD (success)
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="main\n",
            )
            result = _git_status_line()
        assert "main" in result

    def test_shows_clean_when_no_changes(self):
        """Shows 'clean' when no changes."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="main\n"),  # branch
                MagicMock(returncode=0, stdout=""),  # status --porcelain
            ]
            result = _git_status_line()
        assert "clean" in result

    def test_shows_changed_count(self):
        """Shows change count when dirty."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="feature\n"),  # branch
                MagicMock(returncode=0, stdout="M file1.py\n?? file2.py\n"),  # status
            ]
            result = _git_status_line()
        assert "2 changed" in result
        assert "feature" in result

    def test_handles_detached_head(self):
        """Handles detached HEAD state."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=1, stdout=""),  # symbolic-ref fails
                MagicMock(returncode=0, stdout="abc1234\n"),  # rev-parse
                MagicMock(returncode=0, stdout=""),  # status
            ]
            result = _git_status_line()
        assert "abc1234" in result
        assert "detached" in result


class TestStatusWithGit:
    """Tests for /status command including git info."""

    def test_status_includes_git_when_available(self):
        """Status shows git info when _git_status_line returns something."""
        with patch("src.repl._git_status_line", return_value="main (clean)"):
            output = _format_status_output(
                model="test-model",
                cwd="/tmp",
                messages=[{"role": "system", "content": "hi"}],
                usage=MagicMock(
                    input_tokens=100,
                    output_tokens=50,
                    __str__=lambda self: "100+50",
                ),
                skills_count=2,
                context_tokens=150,
            )
        assert "git:" in output
        assert "main (clean)" in output

    def test_status_omits_git_when_not_available(self):
        """Status omits git line when not in a repo."""
        with patch("src.repl._git_status_line", return_value=None):
            output = _format_status_output(
                model="test-model",
                cwd="/tmp",
                messages=[{"role": "system", "content": "hi"}],
                usage=MagicMock(
                    input_tokens=100,
                    output_tokens=50,
                    __str__=lambda self: "100+50",
                ),
                skills_count=0,
                context_tokens=100,
            )
        assert "git:" not in output
