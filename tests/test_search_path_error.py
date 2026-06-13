"""Tests for tool_search error reporting.

Searching a nonexistent path should return a clear, actionable error
([ERROR] Path not found: ...) rather than leaking ripgrep's raw IO error
message, which the LLM can't easily interpret.
"""

import os

from src.tools import tool_search


def test_search_nonexistent_path_clear_error(tmp_path):
    """Searching a path that doesn't exist returns a clear not-found error."""
    missing = str(tmp_path / "does_not_exist")
    result = tool_search("foo", path=missing)
    assert result.startswith("[ERROR]"), f"expected error, got: {result!r}"
    assert "not found" in result.lower() or "no such file" in result.lower(), (
        f"error should mention the missing path, got: {result!r}"
    )
    # Should name the path so the LLM knows what went wrong
    assert missing in result or "does_not_exist" in result, (
        f"error should include the bad path, got: {result!r}"
    )


def test_search_nonexistent_path_does_not_leak_rg_io_error(tmp_path):
    """The raw ripgrep 'IO error ... os error 2' wording is confusing."""
    missing = str(tmp_path / "nope")
    result = tool_search("foo", path=missing)
    # Should not surface the raw ripgrep internal phrasing
    assert "IO error for operation" not in result, (
        f"should translate rg error to plain message, got: {result!r}"
    )


def test_search_valid_path_still_works(tmp_path):
    """Regression guard: searching an existing path still finds matches."""
    (tmp_path / "f.txt").write_text("hello world\nfoo bar\n")
    result = tool_search("foo", path=str(tmp_path))
    assert "foo bar" in result
