"""Test /pr command — generate PR description from git changes."""

import os
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from src.repl import _run_pr_description


def _mock_git_result(returncode=0, stdout="", stderr=""):
    """Create a mock CompletedProcess for git commands."""
    return MagicMock(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


class TestPRDescription:
    """Tests for the /pr command."""

    def test_not_a_git_repo(self):
        """Returns error when not in a git repo."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = _mock_git_result(returncode=1)
            result = _run_pr_description()
            assert "Not a git repo" in result

    def test_no_changes(self):
        """Returns message when there are no changes."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                _mock_git_result(returncode=0),  # rev-parse
                _mock_git_result(returncode=0, stdout=""),  # diff
                _mock_git_result(returncode=0, stdout=""),  # diff --cached
            ]
            result = _run_pr_description()
            assert "No changes" in result

    def test_unstaged_changes_generates_description(self):
        """Generates PR description from unstaged changes."""
        diff_output = "diff --git a/hello.py b/hello.py\n+print('hello')\n"
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                _mock_git_result(returncode=0),  # rev-parse
                _mock_git_result(returncode=0, stdout=diff_output),  # diff
                _mock_git_result(returncode=0, stdout=""),  # diff --cached
                _mock_git_result(returncode=0, stdout="feature-branch\n"),  # branch
                _mock_git_result(returncode=0, stdout="3\n"),  # rev-list --count main..HEAD
                _mock_git_result(returncode=0, stdout="fix: update hello\nfeat: add world\ndocs: readme\n"),  # log
                _mock_git_result(returncode=0, stdout=" hello.py | 1 +\n 1 file changed, 1 insertion(+)\n"),  # diff --stat
            ]
            result = _run_pr_description()
            assert "feature-branch" in result
            assert "hello.py" in result

    def test_staged_changes_only(self):
        """Generates PR description from staged changes only."""
        diff_cached = "diff --git a/bye.py b/bye.py\n+print('bye')\n"
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                _mock_git_result(returncode=0),  # rev-parse
                _mock_git_result(returncode=0, stdout=""),  # diff
                _mock_git_result(returncode=0, stdout=diff_cached),  # diff --cached
                _mock_git_result(returncode=0, stdout="main\n"),  # branch
                _mock_git_result(returncode=0, stdout="1\n"),  # rev-list count
                _mock_git_result(returncode=0, stdout="feat: add bye\n"),  # log
                _mock_git_result(returncode=0, stdout=" bye.py | 1 +\n 1 file changed, 1 insertion(+)\n"),  # diff --stat
            ]
            result = _run_pr_description()
            assert "bye.py" in result

    def test_combined_changes(self):
        """Generates PR description from both staged and unstaged."""
        diff1 = "diff --git a/a.py b/a.py\n+pass\n"
        diff2 = "diff --git a/b.py b/b.py\n+pass\n"
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                _mock_git_result(returncode=0),  # rev-parse
                _mock_git_result(returncode=0, stdout=diff1),  # diff
                _mock_git_result(returncode=0, stdout=diff2),  # diff --cached
                _mock_git_result(returncode=0, stdout="feature\n"),  # branch
                _mock_git_result(returncode=0, stdout="2\n"),  # rev-list count
                _mock_git_result(returncode=0, stdout="commit1\ncommit2\n"),  # log
                _mock_git_result(returncode=0, stdout=" a.py | 1 +\n b.py | 1 +\n"),  # diff --stat
            ]
            result = _run_pr_description()
            assert "feature" in result
            assert "a.py" in result

    def test_truncates_large_diff(self):
        """Truncates very large diffs in PR description."""
        huge_diff = "diff --git a/big.py b/big.py\n" + "+line\n" * 10000
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                _mock_git_result(returncode=0),  # rev-parse
                _mock_git_result(returncode=0, stdout=huge_diff),  # diff
                _mock_git_result(returncode=0, stdout=""),  # diff --cached
                _mock_git_result(returncode=0, stdout="main\n"),  # branch
                _mock_git_result(returncode=0, stdout="1\n"),  # rev-list count
                _mock_git_result(returncode=0, stdout="big change\n"),  # log
                _mock_git_result(returncode=0, stdout=" big.py | 10000 +\n"),  # diff --stat
            ]
            result = _run_pr_description()
            # Should not contain the entire huge diff
            assert len(result) < len(huge_diff) + 1000
