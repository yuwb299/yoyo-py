"""Tests for tool_bash workdir validation.

When workdir doesn't exist or is a file, subprocess raises FileNotFoundError
or NotADirectoryError with cryptic errno messages ("[Errno 2]", "[Errno 20]").
The LLM can't interpret these. We should catch them and return a clear,
actionable message naming the bad workdir.
"""

import os

from src.tools import tool_bash


def test_bash_nonexistent_workdir_clear_message(tmp_path):
    """workdir that doesn't exist should produce a clear message, not Errno 2."""
    missing = str(tmp_path / "no_such_dir")
    result = tool_bash("pwd", workdir=missing)
    assert result.startswith("[ERROR]"), f"expected error, got: {result!r}"
    # Should NOT contain the cryptic errno phrasing
    assert "Errno 2" not in result, (
        f"should translate Errno 2 to plain English, got: {result!r}"
    )
    # Should mention the workdir and that it's missing
    assert missing in result or "workdir" in result.lower() or "directory" in result.lower(), (
        f"should name the bad workdir, got: {result!r}"
    )


def test_bash_workdir_is_file_clear_message(tmp_path):
    """workdir pointing at a file (not a directory) → clear message, not Errno 20."""
    file_path = tmp_path / "afile.txt"
    file_path.write_text("x")
    result = tool_bash("pwd", workdir=str(file_path))
    assert result.startswith("[ERROR]"), f"expected error, got: {result!r}"
    assert "Errno 20" not in result, (
        f"should translate Errno 20 to plain English, got: {result!r}"
    )


def test_bash_valid_workdir_still_works(tmp_path):
    """Regression guard: a valid workdir still runs the command."""
    result = tool_bash("pwd", workdir=str(tmp_path))
    assert str(tmp_path) in result, f"valid workdir should work, got: {result!r}"
    assert "[ERROR]" not in result, f"valid workdir should not error, got: {result!r}"


def test_bash_default_workdir_still_works():
    """Regression guard: default workdir (cwd) still works."""
    result = tool_bash("echo ok")
    assert "ok" in result
    assert "[ERROR]" not in result
