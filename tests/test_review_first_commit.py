"""Tests for /review --commit with edge cases (first commit, empty tree)."""

import subprocess
from unittest.mock import patch, MagicMock
from src.repl import _run_review


class TestReviewFirstCommit:
    """/review --commit should work even for the very first commit."""

    def _mock_completed_process(self, returncode=0, stdout="", stderr=""):
        """Create a mock CompletedProcess."""
        return subprocess.CompletedProcess(
            args=["git"],
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )

    @patch("src.repl._run_git")
    def test_review_first_commit_uses_empty_tree(self, mock_git):
        """When HEAD~1 doesn't exist, should fall back to diff against empty tree."""
        def side_effect(*args, **kwargs):
            cmd_args = list(args)
            if "rev-parse" in cmd_args:
                return self._mock_completed_process(returncode=0, stdout="true\n")
            if "HEAD~1" in cmd_args:
                # No parent commit exists
                return self._mock_completed_process(returncode=128, stderr="fatal: bad revision")
            # git diff <empty-tree-hash> HEAD — the fallback
            if cmd_args[0] == "diff" and cmd_args[-1] == "HEAD":
                return self._mock_completed_process(returncode=0, stdout="diff --git a/file.py\n+new content")
            return self._mock_completed_process(returncode=0, stdout="")

        mock_git.side_effect = side_effect
        result = _run_review(commit=True)
        assert not result.startswith("[ERROR]")
        assert "review" in result.lower() or "diff" in result.lower()

    @patch("src.repl._run_git")
    def test_review_first_commit_shows_diff_content(self, mock_git):
        """Should diff against git's well-known empty tree hash for first commit."""
        def side_effect(*args, **kwargs):
            cmd_args = list(args)
            if "rev-parse" in cmd_args:
                return self._mock_completed_process(returncode=0, stdout="true\n")
            if "HEAD~1" in cmd_args:
                return self._mock_completed_process(returncode=128, stderr="fatal: bad revision")
            # The empty tree hash fallback
            if cmd_args[0] == "diff" and len(cmd_args) >= 3:
                return self._mock_completed_process(
                    returncode=0,
                    stdout="diff --git a/README.md\n+Hello World\n"
                )
            return self._mock_completed_process(returncode=0, stdout="")

        mock_git.side_effect = side_effect
        result = _run_review(commit=True)
        assert "Hello World" in result
        assert "review" in result.lower()

    @patch("src.repl._run_git")
    def test_review_commit_normal(self, mock_git):
        """Normal /review --commit should still work."""
        def side_effect(*args, **kwargs):
            cmd_args = list(args)
            if "rev-parse" in cmd_args:
                return self._mock_completed_process(returncode=0, stdout="true\n")
            if "HEAD~1" in cmd_args:
                return self._mock_completed_process(
                    returncode=0,
                    stdout="diff --git a/file.py\n-old\n+new\n"
                )
            return self._mock_completed_process(returncode=0, stdout="")

        mock_git.side_effect = side_effect
        result = _run_review(commit=True)
        assert "review" in result.lower()
        assert "file.py" in result

    @patch("src.repl._run_git")
    def test_review_commit_nothing_to_review(self, mock_git):
        """If the commit has no diff content, should return a clear message."""
        def side_effect(*args, **kwargs):
            cmd_args = list(args)
            if "rev-parse" in cmd_args:
                return self._mock_completed_process(returncode=0, stdout="true\n")
            if "HEAD~1" in cmd_args:
                return self._mock_completed_process(returncode=0, stdout="")
            if "--cached" in cmd_args:
                return self._mock_completed_process(returncode=0, stdout="")
            if "hash-object" in cmd_args:
                return self._mock_completed_process(
                    returncode=0,
                    stdout="4b825dc642cb6eb9a060e54bf899d15363d7aa72\n"
                )
            return self._mock_completed_process(returncode=0, stdout="")

        mock_git.side_effect = side_effect
        result = _run_review(commit=True)
        # Should indicate nothing to review
        assert result.startswith("[")
