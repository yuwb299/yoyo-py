"""Tests for /review --staged support."""

import subprocess
from unittest.mock import patch, MagicMock

from src.repl import _run_review


class TestReviewStaged:
    """Test /review --staged command support."""

    @patch("src.repl.subprocess.run")
    def test_staged_flag_reviews_staged_changes(self, mock_run):
        """--staged should review only staged changes (git diff --cached)."""
        # git rev-parse succeeds (we're in a repo)
        rev_parse = MagicMock(returncode=0, stdout="true\n")
        # git diff --cached returns some changes
        diff_cached = MagicMock(returncode=0, stdout="diff --git a/file.py b/file.py\n+new line\n")
        # git diff (unstaged) should NOT be called for --staged
        diff_unstaged = MagicMock(returncode=0, stdout="unstaged change that should be ignored\n")

        def _mock_run(cmd, **kwargs):
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
            if "rev-parse" in cmd_str:
                return rev_parse
            if "--cached" in cmd_str and "HEAD~1" not in cmd_str:
                return diff_cached
            if cmd == ["git", "diff"]:
                return diff_unstaged
            return MagicMock(returncode=0, stdout="")

        mock_run.side_effect = _mock_run

        result = _run_review(staged=True)
        assert result is not None
        assert "new line" in result
        assert "review" in result.lower()

    @patch("src.repl.subprocess.run")
    def test_staged_no_changes(self, mock_run):
        """--staged with no staged changes should report no changes."""
        rev_parse = MagicMock(returncode=0, stdout="true\n")
        diff_cached = MagicMock(returncode=0, stdout="")

        def _mock_run(cmd, **kwargs):
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
            if "rev-parse" in cmd_str:
                return rev_parse
            if "--cached" in cmd_str:
                return diff_cached
            return MagicMock(returncode=0, stdout="")

        mock_run.side_effect = _mock_run

        result = _run_review(staged=True)
        assert "No staged changes to review" in result

    @patch("src.repl.subprocess.run")
    def test_staged_not_a_repo(self, mock_run):
        """--staged outside a git repo should report error."""
        rev_parse = MagicMock(returncode=1, stdout="", stderr="not a repo\n")
        mock_run.return_value = rev_parse

        result = _run_review(staged=True)
        assert "Not a git repo" in result

    @patch("src.repl.subprocess.run")
    def test_default_review_unchanged(self, mock_run):
        """Default /review (no flags) should still work as before — review unstaged + staged."""
        rev_parse = MagicMock(returncode=0, stdout="true\n")
        diff = MagicMock(returncode=0, stdout="unstaged diff content\n")
        diff_cached = MagicMock(returncode=0, stdout="staged diff content\n")

        def _mock_run(cmd, **kwargs):
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
            if "rev-parse" in cmd_str:
                return rev_parse
            if cmd == ["git", "diff"]:
                return diff
            if cmd == ["git", "diff", "--cached"]:
                return diff_cached
            return MagicMock(returncode=0, stdout="")

        mock_run.side_effect = _mock_run

        result = _run_review()
        assert "unstaged diff content" in result
        assert "staged diff content" in result
