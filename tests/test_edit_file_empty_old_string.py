"""Tests for edit_file edge case: empty old_string should be rejected.

Empty old_string matches between every character in Python's str.replace(),
which corrupts files. We should reject it with a clear error message.
"""

import tempfile
import os
import pytest
from src.tools import tool_edit_file


class TestEditFileEmptyOldString:
    """Empty old_string is ambiguous and dangerous — reject it."""

    def setup_method(self):
        """Create a temp file for each test."""
        self.tmpfile = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        )
        self.tmpfile.write("hello world\n")
        self.tmpfile.close()
        self.tmppath = self.tmpfile.name

    def teardown_method(self):
        os.unlink(self.tmppath)

    def test_empty_old_string_rejected(self):
        """Empty old_string should produce an error, not corrupt the file."""
        result = tool_edit_file(self.tmppath, "", "X")
        assert "[ERROR]" in result
        # File should be unchanged
        with open(self.tmppath) as f:
            assert f.read() == "hello world\n"

    def test_empty_old_string_replace_all_rejected(self):
        """Empty old_string with replace_all should also be rejected."""
        result = tool_edit_file(self.tmppath, "", "X", replace_all=True)
        assert "[ERROR]" in result
        # File should be unchanged
        with open(self.tmppath) as f:
            assert f.read() == "hello world\n"

    def test_whitespace_old_string_works(self):
        """Non-empty whitespace old_string should still work (not empty)."""
        result = tool_edit_file(self.tmppath, " ", "__")
        assert "[OK]" in result
        with open(self.tmppath) as f:
            assert f.read() == "hello__world\n"

    def test_nonempty_old_string_works(self):
        """Normal (non-empty) old_string should still work fine."""
        result = tool_edit_file(self.tmppath, "hello", "goodbye")
        assert "[OK]" in result
        with open(self.tmppath) as f:
            assert f.read() == "goodbye world\n"
