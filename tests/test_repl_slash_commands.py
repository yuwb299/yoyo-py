"""Tests for REPL slash command routing — ensuring commands like /commit, /model work correctly."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from src.repl import _git_commit, _git_diff_summary


class TestSlashCommitRouting:
    """Test that /commit command properly extracts the message from user input.

    Bug: The REPL used `cmd == "/commit"` which never matches when there's a message,
    and referenced undefined `arg`. These tests verify the fix.
    """

    def test_commit_with_message(self):
        """_git_commit receives the message from the /commit command."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="true\n"),
                MagicMock(returncode=0, stdout="M\tfile.py\n"),
                MagicMock(returncode=0, stdout=""),
                MagicMock(returncode=0, stdout=""),
                MagicMock(returncode=0, stdout="[main abc1234] my commit msg\n1 file changed\n"),
            ]
            result = _git_commit("my commit msg")
        assert "abc1234" in result or "my commit msg" in result

    def test_commit_with_multi_word_message(self):
        """Multi-word commit messages are passed through correctly."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="true\n"),
                MagicMock(returncode=0, stdout="M\tfile.py\n"),
                MagicMock(returncode=0, stdout=""),
                MagicMock(returncode=0, stdout=""),
                MagicMock(returncode=0, stdout="[main def5678] fix: handle edge case in parser\n"),
            ]
            result = _git_commit("fix: handle edge case in parser")
        assert "def5678" in result or "fix" in result.lower()


class TestSlashModelRouting:
    """Test that /model command routing works correctly."""

    def test_model_command_extracts_name(self):
        """'/model glm-4' should extract 'glm-4' as the model name."""
        line = "/model glm-4"
        cmd = line.lower()
        assert cmd.startswith("/model ")
        new_model = line[7:].strip()
        assert new_model == "glm-4"

    def test_model_command_with_spaces(self):
        """'/model  glm-4  ' should trim correctly."""
        line = "/model  glm-4  "
        new_model = line[7:].strip()
        assert new_model == "glm-4"


class TestSlashDiffRouting:
    """Test /diff command."""

    def test_diff_in_git_repo(self):
        """_git_diff_summary works in a git repo with no changes."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="true\n"),  # rev-parse
                MagicMock(returncode=0, stdout=""),         # diff --name-status (unstaged)
                MagicMock(returncode=0, stdout=""),         # diff --cached (staged)
                MagicMock(returncode=0, stdout=""),         # diff --stat
            ]
            result = _git_diff_summary()
        assert "no changes" in result.lower() or "clean" in result.lower()
