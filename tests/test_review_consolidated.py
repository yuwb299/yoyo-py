"""Tests for consolidated /review command routing.

Verifies that /review, /review --commit, and /review --staged are all handled
by a single code path instead of two separate elif blocks.
"""

import pytest
from unittest.mock import patch, MagicMock

from src.repl import _run_review


class TestReviewCommandRouting:
    """Test that all /review variants work correctly."""

    @patch("src.repl._run_git")
    def test_review_bare_calls_run_review_no_args(self, mock_git):
        """`/review` (no args) reviews unstaged + staged changes."""
        mock_git.return_value = MagicMock(returncode=1)
        result = _run_review()
        # Not a git repo in test — should return error, not crash
        assert "Not a git repo" in result

    @patch("src.repl._run_git")
    def test_review_commit_flag(self, mock_git):
        """`/review --commit` calls with commit=True."""
        mock_git.return_value = MagicMock(returncode=1)
        result = _run_review(commit=True)
        assert "Not a git repo" in result

    @patch("src.repl._run_git")
    def test_review_staged_flag(self, mock_git):
        """`/review --staged` calls with staged=True."""
        mock_git.return_value = MagicMock(returncode=1)
        result = _run_review(staged=True)
        assert "Not a git repo" in result

    @patch("src.repl._run_git")
    def test_review_with_diff(self, mock_git):
        """`/review` with actual diff returns review prompt."""
        results = {
            ("rev-parse", "--is-inside-work-tree"): MagicMock(returncode=0, stdout="true"),
            ("diff",): MagicMock(returncode=0, stdout="diff --git a/foo.py\n+new line"),
            ("diff", "--cached"): MagicMock(returncode=0, stdout=""),
        }

        def side_effect(*args, **kwargs):
            key = tuple(args)
            return results.get(key, MagicMock(returncode=0, stdout=""))

        mock_git.side_effect = side_effect
        result = _run_review()
        assert "review" in result.lower()
        assert "new line" in result

    @patch("src.repl._run_git")
    def test_review_clean_tree(self, mock_git):
        """`/review` with no changes returns clean message."""
        mock_git.return_value = MagicMock(returncode=0, stdout="")
        result = _run_review()
        assert "No changes" in result
