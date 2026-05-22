"""Tests for the /commit REPL command helper."""

import pytest
from unittest.mock import patch, MagicMock
from src.repl import _git_commit


def _mock_completed(**kwargs):
    """Helper to create a mock subprocess.CompletedProcess."""
    return MagicMock(returncode=kwargs.get("returncode", 0),
                     stdout=kwargs.get("stdout", ""),
                     stderr=kwargs.get("stderr", ""))


class TestGitCommit:
    """Test the /commit command helper."""

    def test_no_git_repo(self):
        """Returns error when not in a git repo."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = _mock_completed(returncode=128, stderr="fatal: not a git repository")
            result = _git_commit("test message")
        assert "not a git repo" in result.lower()

    def test_no_changes(self):
        """Returns error when there's nothing to commit."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                _mock_completed(returncode=0, stdout="true\n"),  # rev-parse
                _mock_completed(returncode=1, stdout=""),         # git diff (no changes)
            ]
            result = _git_commit("test message")
        assert "no changes" in result.lower()

    def test_commit_success(self):
        """Successful commit returns confirmation."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                _mock_completed(returncode=0, stdout="true\n"),                    # rev-parse
                _mock_completed(returncode=0, stdout="M\tsrc/agent.py\n"),         # diff --name-status
                _mock_completed(returncode=0, stdout=""),                          # git add -A
                _mock_completed(returncode=0,                                      # git commit
                                stdout="[main abc1234] test message\n 1 file changed, 2 insertions(+)\n"),
            ]
            result = _git_commit("test message")
        assert "abc1234" in result or "commit" in result.lower()

    def test_commit_with_empty_message_fails(self):
        """Empty commit message is rejected."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                _mock_completed(returncode=0, stdout="true\n"),   # rev-parse
                _mock_completed(returncode=0, stdout="M\tf.py\n"),  # diff --name-status
                _mock_completed(returncode=0, stdout=""),          # git add -A
                _mock_completed(returncode=1, stderr="empty commit message"),  # git commit fails
            ]
            result = _git_commit("")
        assert "error" in result.lower() or "failed" in result.lower()
