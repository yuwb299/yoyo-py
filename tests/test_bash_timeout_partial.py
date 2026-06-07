"""Tests for bash tool timeout preserving partial output.

When a command times out, the bash tool should capture whatever stdout/stderr
was produced before the timeout, rather than discarding it all.
"""

import subprocess
import unittest
from unittest.mock import patch, MagicMock

from src.tools import tool_bash


class TestBashTimeoutPartialOutput(unittest.TestCase):
    """Test that tool_bash captures partial output on timeout."""

    @patch("src.tools.subprocess.run")
    def test_timeout_shows_partial_stdout(self, mock_run):
        """On timeout, partial stdout should be included in the error message."""
        exc = subprocess.TimeoutExpired(
            cmd="sleep 999", timeout=5, output=b"partial output here"
        )
        mock_run.side_effect = exc

        result = tool_bash("sleep 999", timeout=5)
        # Should include the partial output
        self.assertIn("partial output here", result)
        self.assertIn("[TIMEOUT]", result)

    @patch("src.tools.subprocess.run")
    def test_timeout_with_stderr(self, mock_run):
        """On timeout, partial stderr should be included."""
        exc = subprocess.TimeoutExpired(
            cmd="cmd", timeout=5, output=b"out", stderr=b"err output"
        )
        mock_run.side_effect = exc

        result = tool_bash("cmd", timeout=5)
        self.assertIn("err output", result)
        self.assertIn("[TIMEOUT]", result)

    @patch("src.tools.subprocess.run")
    def test_timeout_no_partial_output(self, mock_run):
        """On timeout with no output, show clean timeout message."""
        exc = subprocess.TimeoutExpired(cmd="cmd", timeout=5)
        mock_run.side_effect = exc

        result = tool_bash("cmd", timeout=5)
        self.assertIn("[TIMEOUT]", result)
        self.assertEqual(result.strip(), f"[TIMEOUT] Command timed out after 5s")

    @patch("src.tools.subprocess.run")
    def test_timeout_with_bytes_output(self, mock_run):
        """On timeout, byte output should be decoded to string."""
        exc = subprocess.TimeoutExpired(
            cmd="cmd", timeout=5, output="部分输出".encode("utf-8")
        )
        mock_run.side_effect = exc

        result = tool_bash("cmd", timeout=5)
        self.assertIn("部分输出", result)

    @patch("src.tools.subprocess.run")
    def test_timeout_with_string_output(self, mock_run):
        """On timeout with text=True, output is a string — should handle gracefully."""
        exc = subprocess.TimeoutExpired(
            cmd="cmd", timeout=5, output="string partial output"
        )
        mock_run.side_effect = exc

        result = tool_bash("cmd", timeout=5)
        self.assertIn("string partial output", result)


if __name__ == "__main__":
    unittest.main()
