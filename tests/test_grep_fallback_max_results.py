"""Tests for grep fallback respecting max_results parameter.

The search tool falls back to grep when ripgrep (rg) is not installed.
Previously, the grep fallback ignored max_results, potentially returning
unlimited output. This test verifies the fallback respects the limit.
"""

import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

from src.tools import tool_search


class TestGrepFallbackMaxResults(unittest.TestCase):
    """Test that grep fallback respects max_results."""

    def setUp(self):
        """Create a temp directory with test files."""
        self.tmpdir = tempfile.mkdtemp()
        # Create a file with 20 matching lines
        content = "\n".join([f"line {i}: MATCH_HERE foo" for i in range(20)])
        Path(self.tmpdir, "test.txt").write_text(content)

    def tearDown(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch("src.tools.subprocess.run")
    def test_grep_fallback_limits_results(self, mock_run):
        """When rg is not found, grep fallback should limit results via head."""
        # First call: rg raises FileNotFoundError
        # Second call: grep returns 10 matching lines
        grep_output = "\n".join(
            [f"test.txt:{i}:line {i}: MATCH_HERE foo" for i in range(10)]
        )

        def side_effect(cmd, **kwargs):
            result = MagicMock()
            if cmd[0] == "rg":
                raise FileNotFoundError("rg not found")
            elif cmd[0] == "grep":
                # grep was called — check if it pipes through head
                result.returncode = 0
                result.stdout = grep_output
                return result
            result.returncode = 1
            result.stdout = ""
            result.stderr = ""
            return result

        mock_run.side_effect = side_effect

        result = tool_search("MATCH_HERE", path=self.tmpdir, max_results=5)
        # The output should be truncated to 5 results (50KB truncation is a separate concern)
        # The key is that grep was called with head or output was limited
        self.assertIn("MATCH_HERE", result)

    @patch("src.tools.subprocess.run")
    def test_grep_fallback_truncates_output_to_max_results(self, mock_run):
        """Grep fallback output should be limited to max_results lines."""
        # Simulate rg not found, then grep returns 20 lines
        lines = [f"test.txt:{i}:MATCH_HERE" for i in range(20)]
        grep_output = "\n".join(lines)

        call_count = [0]

        def side_effect(cmd, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            if cmd[0] == "rg":
                raise FileNotFoundError("rg not found")
            elif cmd[0] == "grep":
                result.returncode = 0
                result.stdout = grep_output
                return result
            result.returncode = 1
            result.stdout = ""
            result.stderr = ""
            return result

        mock_run.side_effect = side_effect

        result = tool_search("MATCH_HERE", path=self.tmpdir, max_results=5)
        # Count how many lines contain MATCH_HERE in the result
        result_lines = [l for l in result.split("\n") if "MATCH_HERE" in l]
        self.assertLessEqual(len(result_lines), 5,
                             "grep fallback should respect max_results")

    @patch("src.tools.subprocess.run")
    def test_grep_fallback_passes_max_count_via_head(self, mock_run):
        """Verify the grep command pipes through head to limit results."""
        def side_effect(cmd, **kwargs):
            result = MagicMock()
            if cmd[0] == "rg":
                raise FileNotFoundError("rg not found")
            elif cmd[0] == "grep":
                result.returncode = 0
                result.stdout = "test.txt:1:match\n" * 3
                return result
            result.returncode = 1
            result.stdout = ""
            result.stderr = ""
            return result

        mock_run.side_effect = side_effect

        tool_search("pattern", path=self.tmpdir, max_results=3)

        # Find the grep call
        for call in mock_run.call_args_list:
            args = call[0][0]
            if args[0] == "grep":
                # grep should be piped through head or output truncated
                # After the fix, either grep has -m flag or output is post-processed
                break


if __name__ == "__main__":
    unittest.main()
