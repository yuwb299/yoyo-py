"""Tests for /selfassess command.

Validates that the self-assessment diagnostic command produces
a useful summary including code stats, test results, and known issues.
"""

import subprocess
from unittest.mock import patch, MagicMock

import pytest
from src.repl import _run_selfassess


class TestSelfassessFormat:
    """Test output format and content of /selfassess."""

    @staticmethod
    def _mock_subprocess_run(*args, **kwargs):
        """Mock subprocess.run to avoid actually running pytest."""
        cmd = args[0] if args else kwargs.get("args", [])

        # Mock git rev-parse
        if cmd[:2] == ["git", "rev-parse"]:
            r = MagicMock()
            r.returncode = 0
            r.stdout = "main\n"
            r.stderr = ""
            return r

        # Mock git log
        if cmd[:2] == ["git", "log"]:
            r = MagicMock()
            r.returncode = 0
            r.stdout = "abc1234 Day 44: something\ndef5678 Day 43: other\n"
            r.stderr = ""
            return r

        # Mock pytest — return quickly
        if "pytest" in str(cmd):
            r = MagicMock()
            r.returncode = 0
            r.stdout = "1108 passed in 0.01s\n"
            r.stderr = ""
            return r

        # Default: command not found
        raise FileNotFoundError(f"{cmd[0]} not found")

    @pytest.fixture(autouse=True)
    def mock_subprocess(self):
        """Mock subprocess.run for all tests to avoid slow real commands."""
        with patch("subprocess.run", side_effect=self._mock_subprocess_run):
            yield

    def test_returns_nonempty_string(self):
        """Self-assessment should produce non-empty output."""
        result = _run_selfassess()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_header(self):
        """Output should have a clear header."""
        result = _run_selfassess()
        assert "Self-Assessment" in result or "self-assessment" in result.lower()

    def test_contains_code_stats(self):
        """Output should include code statistics."""
        result = _run_selfassess()
        assert "lines" in result.lower() or "files" in result.lower() or "LOC" in result

    def test_contains_test_info(self):
        """Output should include test results or test count."""
        result = _run_selfassess()
        assert "test" in result.lower()

    def test_contains_known_issues_scan(self):
        """Output should scan for TODOs/FIXMEs."""
        result = _run_selfassess()
        # Either found issues or reports clean
        assert "TODO" in result or "FIXME" in result or "clean" in result.lower() or "issue" in result.lower()

    def test_contains_git_info(self):
        """Output should include git branch or recent commits."""
        result = _run_selfassess()
        assert "branch" in result.lower() or "commit" in result.lower() or "git" in result.lower()

    def test_contains_model_info(self):
        """Output should include model or context window info."""
        result = _run_selfassess()
        assert "model" in result.lower() or "context" in result.lower()

    def test_no_exceptions_on_missing_git(self):
        """Should not crash if subprocess fails entirely."""
        with patch("subprocess.run", side_effect=FileNotFoundError("not found")):
            result = _run_selfassess()
            assert isinstance(result, str)


class TestSelfassessRegistration:
    """Test that /selfassess is properly registered as a command."""

    def test_selfassess_in_slash_commands(self):
        """'/selfassess' should appear in the slash command list."""
        from src.repl import _SLASH_COMMANDS
        assert "/selfassess" in _SLASH_COMMANDS
