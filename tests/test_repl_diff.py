"""Tests for the /diff REPL command."""

import pytest
from unittest.mock import patch, MagicMock
from src.repl import _git_diff_summary


def _mock_completed(**kwargs):
    """Helper to create a mock subprocess.CompletedProcess."""
    return MagicMock(returncode=kwargs.get("returncode", 0),
                     stdout=kwargs.get("stdout", ""),
                     stderr=kwargs.get("stderr", ""))


class TestGitDiffSummary:
    """Test the git diff summary generator."""

    def test_no_git_repo(self):
        """Returns error message when not in a git repo."""
        with patch("subprocess.run") as mock_run:
            # rev-parse fails
            mock_run.return_value = _mock_completed(returncode=128, stderr="fatal: not a git repository")
            result = _git_diff_summary()
        assert "not a git repo" in result.lower()

    def test_clean_repo(self):
        """Returns 'no changes' when repo is clean."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                _mock_completed(returncode=0, stdout="true\n"),  # rev-parse: inside work tree
                _mock_completed(returncode=0, stdout=""),        # diff --name-status: empty
                _mock_completed(returncode=0, stdout=""),        # diff --cached: empty
            ]
            result = _git_diff_summary()
        assert "no changes" in result.lower()

    def test_unstaged_changes(self):
        """Shows unstaged file changes."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                _mock_completed(returncode=0, stdout="true\n"),                # rev-parse
                _mock_completed(returncode=0, stdout="M\tsrc/agent.py\nA\tnew_file.py\nD\told_file.py\n"),  # diff
                _mock_completed(returncode=0, stdout=""),                      # diff --cached: empty
                _mock_completed(returncode=0, stdout=" src/agent.py | 5 +--\n"),  # diff --stat
            ]
            result = _git_diff_summary()
        assert "agent.py" in result
        assert "new_file.py" in result
        assert "old_file.py" in result
        assert "unstaged" in result.lower()

    def test_staged_changes(self):
        """Shows staged file changes with indicator."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                _mock_completed(returncode=0, stdout="true\n"),           # rev-parse
                _mock_completed(returncode=0, stdout=""),                # diff --name-status: clean
                _mock_completed(returncode=0, stdout="M\tsrc/tools.py\n"),  # diff --cached
                _mock_completed(returncode=0, stdout=" src/tools.py | 3 ++-\n"),  # diff --stat
            ]
            result = _git_diff_summary()
        assert "tools.py" in result
        assert "staged" in result.lower()

    def test_both_staged_and_unstaged(self):
        """Shows both staged and unstaged changes."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                _mock_completed(returncode=0, stdout="true\n"),           # rev-parse
                _mock_completed(returncode=0, stdout="M\tsrc/agent.py\n"),  # diff
                _mock_completed(returncode=0, stdout="A\tnew_file.py\n"),  # diff --cached
                _mock_completed(returncode=0, stdout=" 2 files changed\n"),  # diff --stat
            ]
            result = _git_diff_summary()
        assert "agent.py" in result
        assert "new_file.py" in result

    def test_diff_stat_included(self):
        """Diff stat is included in the output."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                _mock_completed(returncode=0, stdout="true\n"),           # rev-parse
                _mock_completed(returncode=0, stdout="M\tsrc/agent.py\n"),  # diff
                _mock_completed(returncode=0, stdout=""),                 # diff --cached
                _mock_completed(returncode=0, stdout=" src/agent.py | 5 +---\n 1 file changed, 2 insertions(+), 3 deletions(-)\n"),  # stat
            ]
            result = _git_diff_summary()
        assert "insertions" in result
