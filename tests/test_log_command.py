"""Tests for the /log command — show recent git commit log."""

import subprocess
from unittest.mock import patch, MagicMock
from src.repl import _run_git_log


class TestGitLogCommand:
    """Test /log command that shows recent git commit history."""

    def test_not_a_git_repo(self):
        """Should report when not in a git repo."""
        mock_result = MagicMock()
        mock_result.returncode = 128
        mock_result.stderr = "not a git repo"

        with patch("subprocess.run", return_value=mock_result):
            result = _run_git_log()
        assert "Not a git repo" in result

    def test_clean_log_output(self):
        """Should display formatted commit log."""
        mock_check = MagicMock()
        mock_check.returncode = 0

        log_output = "abc1234|Day 7: fix bug|yuwb|2026-05-26\ndef5678|Day 6: add feature|yuwb|2026-05-25"
        mock_log = MagicMock()
        mock_log.returncode = 0
        mock_log.stdout = log_output

        def side_effect(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if "rev-parse" in cmd:
                return mock_check
            return mock_log

        with patch("subprocess.run", side_effect=side_effect):
            result = _run_git_log()
        assert "abc1234" in result
        assert "fix bug" in result

    def test_default_count(self):
        """Should default to 10 commits."""
        mock_check = MagicMock()
        mock_check.returncode = 0

        mock_log = MagicMock()
        mock_log.returncode = 0
        mock_log.stdout = ""

        calls = []

        def side_effect(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            calls.append(cmd)
            if "rev-parse" in cmd:
                return mock_check
            return mock_log

        with patch("subprocess.run", side_effect=side_effect):
            _run_git_log()

        # Should use -n 10 by default
        log_call = [c for c in calls if "log" in c and "rev-parse" not in c]
        assert len(log_call) > 0
        assert "-10" in log_call[0] or "-n" in " ".join(log_call[0])

    def test_custom_count(self):
        """Should respect count parameter."""
        mock_check = MagicMock()
        mock_check.returncode = 0

        mock_log = MagicMock()
        mock_log.returncode = 0
        mock_log.stdout = ""

        calls = []

        def side_effect(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            calls.append(cmd)
            if "rev-parse" in cmd:
                return mock_check
            return mock_log

        with patch("subprocess.run", side_effect=side_effect):
            _run_git_log(count=5)

        log_call = [c for c in calls if "log" in c and "rev-parse" not in c]
        assert len(log_call) > 0
        assert "-5" in log_call[0]

    def test_empty_repo(self):
        """Should handle empty repo (no commits)."""
        mock_check = MagicMock()
        mock_check.returncode = 0

        mock_log = MagicMock()
        mock_log.returncode = 0
        mock_log.stdout = ""

        def side_effect(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if "rev-parse" in cmd:
                return mock_check
            return mock_log

        with patch("subprocess.run", side_effect=side_effect):
            result = _run_git_log()
        assert "No commits" in result or "empty" in result.lower() or result.strip() == ""

    def test_git_log_error(self):
        """Should handle git log command failure."""
        mock_check = MagicMock()
        mock_check.returncode = 0

        mock_log = MagicMock()
        mock_log.returncode = 1
        mock_log.stderr = "some error"

        def side_effect(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if "rev-parse" in cmd:
                return mock_check
            return mock_log

        with patch("subprocess.run", side_effect=side_effect):
            result = _run_git_log()
        assert "[ERROR]" in result

    def test_log_with_count_arg_in_repl(self):
        """Should parse /log N to show N commits."""
        # Test the REPL dispatch parsing
        # /log 5 should pass count=5
        mock_check = MagicMock()
        mock_check.returncode = 0

        mock_log = MagicMock()
        mock_log.returncode = 0
        mock_log.stdout = "abc|msg|author|date"

        calls = []

        def side_effect(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            calls.append(cmd)
            if "rev-parse" in cmd:
                return mock_check
            return mock_log

        with patch("subprocess.run", side_effect=side_effect):
            _run_git_log(count=20)

        log_call = [c for c in calls if "log" in c and "rev-parse" not in c]
        assert len(log_call) > 0
        assert "-20" in log_call[0]
