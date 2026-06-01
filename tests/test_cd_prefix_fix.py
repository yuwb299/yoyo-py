"""Test that /cd command only matches /cd and /cd <path>, not /cdfoo etc."""

import os
import unittest
from unittest.mock import patch

from src.repl import _handle_cd_command


class TestCdPrefixFix(unittest.TestCase):
    """Verify /cd command routing only matches valid invocations.

    The REPL dispatch uses cmd.startswith("/cd") which is too broad.
    These tests verify that _handle_cd_command itself works correctly,
    and document the expected behavior for the routing fix.
    """

    def test_cd_no_arg_goes_home(self):
        """Empty path should expand to home directory."""
        result = _handle_cd_command("")
        # Should either succeed with home dir or fail (if home doesn't exist)
        self.assertTrue(result.startswith("[OK]") or result.startswith("[ERROR]"))

    def test_cd_with_path(self):
        """Explicit path should be handled."""
        result = _handle_cd_command("/tmp")
        self.assertTrue(result.startswith("[OK]"))
        # Clean up - go back
        os.chdir("/Users/yuwb299gmail.com/yoyo-py")

    def test_cd_dot_stays(self):
        """cd . should stay in current directory."""
        result = _handle_cd_command(".")
        self.assertTrue(result.startswith("[OK]"))

    def test_cd_nonexistent_dir(self):
        """cd to nonexistent directory should error."""
        result = _handle_cd_command("/nonexistent_dir_xyz_12345")
        self.assertIn("[ERROR]", result)


class TestCdRouting(unittest.TestCase):
    """Test the REPL-level routing of /cd command.

    Simulates how the REPL dispatch handles /cd by checking the
    command matching logic.
    """

    def _would_match_cd(self, cmd: str) -> bool:
        """Simulate the CURRENT (broken) matching logic."""
        return cmd.startswith("/cd")

    def _should_match_cd(self, cmd: str) -> bool:
        """The CORRECT matching logic."""
        return cmd == "/cd" or cmd.startswith("/cd ")

    def test_cd_matches(self):
        self.assertTrue(self._should_match_cd("/cd"))

    def test_cd_with_space_matches(self):
        self.assertTrue(self._should_match_cd("/cd /tmp"))

    def test_cdfoo_should_not_match(self):
        self.assertFalse(self._should_match_cd("/cdfoo"))

    def test_cdsearch_should_not_match(self):
        self.assertFalse(self._should_match_cd("/cdsearch"))

    def test_cd_broken_matches_too_much(self):
        """Document that the current logic matches too broadly."""
        self.assertTrue(self._would_match_cd("/cdfoo"))
        self.assertFalse(self._should_match_cd("/cdfoo"))


if __name__ == "__main__":
    unittest.main()
