"""Test /log command --oneline flag support."""

import pytest
from unittest.mock import patch, MagicMock
from src.repl import _run_git_log


class TestLogOneline:
    """Test that /log --oneline works correctly."""

    @patch("src.repl._run_git")
    def test_log_oneline_flag(self, mock_git):
        """--oneline should produce compact single-line log entries."""
        # First call: repo check
        check = MagicMock()
        check.returncode = 0
        # Second call: git log
        log_result = MagicMock()
        log_result.returncode = 0
        log_result.stdout = "abc1234 Fix bug\nxyz9876 Add feature\n"
        mock_git.side_effect = [check, log_result]

        result = _run_git_log(oneline=True)
        assert "abc1234" in result
        assert "xyz9876" in result

    @patch("src.repl._run_git")
    def test_log_default_format(self, mock_git):
        """Default format should show pipe-separated fields."""
        check = MagicMock()
        check.returncode = 0
        log_result = MagicMock()
        log_result.returncode = 0
        log_result.stdout = "abc1234|Fix bug|Alice|2 hours ago\n"
        mock_git.side_effect = [check, log_result]

        result = _run_git_log(count=10)
        assert "abc1234" in result
        assert "Alice" in result
        assert "2 hours ago" in result

    @patch("src.repl._run_git")
    def test_log_with_count_and_oneline(self, mock_git):
        """count and oneline should work together."""
        check = MagicMock()
        check.returncode = 0
        log_result = MagicMock()
        log_result.returncode = 0
        log_result.stdout = "abc1234 msg\n"
        mock_git.side_effect = [check, log_result]

        result = _run_git_log(count=5, oneline=True)
        # Verify the log call used oneline format (%h %s, not pipe-separated)
        log_call = mock_git.call_args_list[1]
        assert any("%h %s" in str(arg) for arg in log_call[0])
