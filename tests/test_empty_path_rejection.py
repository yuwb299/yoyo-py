"""Tests that path-requiring tools reject empty/whitespace paths.

Background: An empty path string ("") is never valid intent for a path
parameter, but Path("").exists() resolves to the current directory (".").
Before this fix, tool_mkdir("") claimed "Directory already exists" — a
silent success on a no-op that the LLM could not distinguish from actually
creating a directory. read_file("") / write_file("") produced cryptic
"Is a directory" / "Not a file" errors. This is a data-integrity class
bug: the agent thinks it did something it didn't.
"""

import os
import tempfile

from src.tools import (
    tool_mkdir,
    tool_read_file,
    tool_write_file,
    tool_copy_file,
    tool_rename,
    tool_edit_file,
)


def _assert_error(result: str, param_hint: str) -> None:
    """An empty-path call must return an [ERROR] message, never an [OK]."""
    assert result.startswith("[ERROR]"), (
        f"Expected [ERROR] for empty path, got success: {result!r}"
    )
    assert param_hint in result.lower(), (
        f"Error message should name the offending param '{param_hint}': {result!r}"
    )


# ── tool_mkdir ──────────────────────────────────────────────────────────


def test_mkdir_empty_string_is_error_not_silent_success():
    # Regression: Path("").exists() is True (resolves to cwd), so the old
    # code returned "[OK] Directory already exists:" — a silent no-op.
    result = tool_mkdir("")
    _assert_error(result, "path")


def test_mkdir_whitespace_only_is_error():
    result = tool_mkdir("   ")
    _assert_error(result, "path")


def test_mkdir_still_creates_valid_dir():
    # Positive control: make sure the fix didn't break normal operation.
    with tempfile.TemporaryDirectory() as d:
        new = os.path.join(d, "newdir")
        result = tool_mkdir(new)
        assert result.startswith("[OK]")
        assert os.path.isdir(new)


# ── tool_read_file ──────────────────────────────────────────────────────


def test_read_file_empty_string_is_error():
    result = tool_read_file("")
    _assert_error(result, "path")


def test_read_file_whitespace_only_is_error():
    result = tool_read_file("   ")
    _assert_error(result, "path")


# ── tool_write_file ─────────────────────────────────────────────────────


def test_write_file_empty_path_is_error():
    result = tool_write_file("", "content")
    _assert_error(result, "path")


def test_write_file_whitespace_only_path_is_error():
    result = tool_write_file("  \t ", "content")
    _assert_error(result, "path")


def test_write_file_still_writes_valid_path():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "f.txt")
        result = tool_write_file(p, "hello")
        assert result.startswith("[OK]")
        assert open(p).read() == "hello"


# ── tool_copy_file ──────────────────────────────────────────────────────


def test_copy_file_empty_source_is_error():
    result = tool_copy_file("", "/tmp/dest")
    _assert_error(result, "source")


def test_copy_file_empty_destination_is_error():
    result = tool_copy_file("/tmp", "")
    _assert_error(result, "destination")


# ── tool_rename ─────────────────────────────────────────────────────────


def test_rename_empty_source_is_error():
    result = tool_rename("", "/tmp/dest")
    _assert_error(result, "source")


def test_rename_empty_destination_is_error():
    result = tool_rename("/tmp", "")
    _assert_error(result, "destination")


# ── tool_edit_file ──────────────────────────────────────────────────────


def test_edit_file_empty_path_is_error():
    result = tool_edit_file("", "a", "b")
    _assert_error(result, "path")
