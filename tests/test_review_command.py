"""Tests for /review command — AI code review of git changes."""

import subprocess
from unittest.mock import patch, MagicMock

from src.repl import _run_review, _review_prompt_from_diff


class TestReviewPromptFromDiff:
    """Test generating a review prompt from a diff."""

    def test_empty_diff_no_changes(self):
        """Return error message when there are no changes."""
        result = _review_prompt_from_diff("")
        assert result is None

    def test_generates_prompt_with_diff(self):
        """Generate a review prompt containing the diff content."""
        diff = "diff --git a/src/main.py b/src/main.py\n+print('hello')"
        result = _review_prompt_from_diff(diff)
        assert result is not None
        assert "review" in result.lower()
        assert "print('hello')" in result

    def test_prompt_includes_review_instructions(self):
        """The generated prompt should include review instructions."""
        diff = "+new line"
        result = _review_prompt_from_diff(diff)
        assert result is not None
        # Should mention common review aspects
        assert any(word in result.lower() for word in ["bug", "security", "style"])


class TestRunReview:
    """Test the _run_review function that gathers diff and builds prompt."""

    @patch("src.repl.subprocess.run")
    def test_not_a_git_repo(self, mock_run):
        """Return error when not in a git repo."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        result = _run_review()
        assert "not a git repo" in result.lower()

    @patch("src.repl.subprocess.run")
    def test_no_changes(self, mock_run):
        """Return message when there are no changes."""
        # First call: git rev-parse (is repo?)
        # Second call: git diff (unstaged)
        # Third call: git diff --cached (staged)
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="true", stderr=""),  # rev-parse
            MagicMock(returncode=0, stdout="", stderr=""),       # diff
            MagicMock(returncode=0, stdout="", stderr=""),       # diff --cached
        ]
        result = _run_review()
        assert "no changes" in result.lower()

    @patch("src.repl.subprocess.run")
    def test_unstaged_changes_generates_prompt(self, mock_run):
        """Generate review prompt for unstaged changes."""
        diff_output = "diff --git a/src/main.py\n+new line\n-old line"
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="true", stderr=""),  # rev-parse
            MagicMock(returncode=0, stdout=diff_output, stderr=""),  # diff
            MagicMock(returncode=0, stdout="", stderr=""),      # diff --cached
        ]
        result = _run_review()
        assert result is not None
        assert "new line" in result

    @patch("src.repl.subprocess.run")
    def test_staged_changes_generates_prompt(self, mock_run):
        """Generate review prompt for staged changes."""
        diff_output = "diff --git a/src/main.py\n+staged change"
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="true", stderr=""),  # rev-parse
            MagicMock(returncode=0, stdout="", stderr=""),      # diff
            MagicMock(returncode=0, stdout=diff_output, stderr=""),  # diff --cached
        ]
        result = _run_review()
        assert result is not None
        assert "staged change" in result

    @patch("src.repl.subprocess.run")
    def test_combined_changes(self, mock_run):
        """Generate review prompt for both staged and unstaged changes."""
        unstaged = "diff --git a/a.py\n+unstaged"
        staged = "diff --git a/b.py\n+staged"
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="true", stderr=""),  # rev-parse
            MagicMock(returncode=0, stdout=unstaged, stderr=""),  # diff
            MagicMock(returncode=0, stdout=staged, stderr=""),    # diff --cached
        ]
        result = _run_review()
        assert "unstaged" in result
        assert "staged" in result

    @patch("src.repl.subprocess.run")
    def test_diff_command_fails(self, mock_run):
        """Handle git diff command failure."""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="true", stderr=""),  # rev-parse
            MagicMock(returncode=1, stdout="", stderr="error"),  # diff failed
            MagicMock(returncode=0, stdout="", stderr=""),       # diff --cached (also called)
        ]
        result = _run_review()
        assert "error" in result.lower()

    @patch("src.repl.subprocess.run")
    def test_truncates_very_large_diff(self, mock_run):
        """Very large diffs should be truncated to avoid blowing up the prompt."""
        large_diff = "diff --git a/big.py\n" + "+line\n" * 5000
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="true", stderr=""),
            MagicMock(returncode=0, stdout=large_diff, stderr=""),
            MagicMock(returncode=0, stdout="", stderr=""),
        ]
        result = _run_review()
        assert result is not None
        # Result should be smaller than the raw diff
        assert len(result) < len(large_diff) + 2000

    @patch("src.repl.subprocess.run")
    def test_commit_option_generates_prompt(self, mock_run):
        """With commit=True, review the last commit's diff."""
        commit_diff = "diff --git a/a.py\n+committed line"
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="true", stderr=""),  # rev-parse
            MagicMock(returncode=0, stdout=commit_diff, stderr=""),  # diff HEAD~1
        ]
        result = _run_review(commit=True)
        assert "committed line" in result

    @patch("src.repl.subprocess.run")
    def test_commit_option_no_commits(self, mock_run):
        """With commit=True but no previous commits, show helpful error."""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="true", stderr=""),  # rev-parse
            MagicMock(returncode=128, stdout="", stderr="fatal: bad revision"),  # diff HEAD~1
            MagicMock(returncode=128, stdout="", stderr="fatal: bad revision"),  # diff --cached HEAD fallback
        ]
        result = _run_review(commit=True)
        assert result is not None  # Should return some message, not crash
