"""Tests for write_file line count and edit_file no-op detection.

Two bugs:
1. write_file with empty content reported "Wrote 1 lines" — the line-count
   formula `count("\n") + 1` yields 1 for empty string. Should report 0.
2. edit_file where old_string == new_string silently succeeds as a no-op.
   This is almost always an LLM mistake (it meant to change something), and
   the silent success hides the bug. Should warn or error.
"""

from src.tools import tool_write_file, tool_edit_file


def test_write_file_empty_content_reports_zero_lines(tmp_path):
    """Empty content → 'Wrote 0 lines', not 'Wrote 1 lines'."""
    f = tmp_path / "empty.txt"
    result = tool_write_file(str(f), "")
    assert "Wrote 0" in result, f"empty content should report 0 lines, got: {result!r}"
    assert f.read_text() == ""


def test_write_file_single_line_no_trailing_newline(tmp_path):
    """Regression guard: 'hello' (no newline) is 1 line."""
    f = tmp_path / "one.txt"
    result = tool_write_file(str(f), "hello")
    assert "Wrote 1" in result, f"single line should report 1, got: {result!r}"


def test_write_file_single_line_with_trailing_newline(tmp_path):
    """Regression guard: 'hello\\n' is 1 line (the trailing newline doesn't add a line)."""
    f = tmp_path / "one.txt"
    result = tool_write_file(str(f), "hello\n")
    assert "Wrote 1" in result, f"'hello\\n' should report 1 line, got: {result!r}"


def test_write_file_three_lines(tmp_path):
    """Regression guard: 'a\\nb\\nc' is 3 lines."""
    f = tmp_path / "three.txt"
    result = tool_write_file(str(f), "a\nb\nc")
    assert "Wrote 3" in result, f"'a\\nb\\nc' should report 3 lines, got: {result!r}"


def test_edit_file_identical_old_new_warns(tmp_path):
    """old_string == new_string is a no-op and almost always a mistake — warn."""
    f = tmp_path / "f.txt"
    f.write_text("hello world\n")
    result = tool_edit_file(str(f), "hello", "hello")
    # Should NOT silently claim success — either error or warn clearly
    assert "[ERROR]" in result or "[WARN]" in result or "no-op" in result.lower() or "identical" in result.lower(), (
        f"identical old/new should warn, got: {result!r}"
    )


def test_edit_file_empty_new_string_still_works(tmp_path):
    """Regression guard: empty new_string is a valid deletion, must still work."""
    f = tmp_path / "f.txt"
    f.write_text("hello world\n")
    result = tool_edit_file(str(f), "hello ", "")
    assert "[OK]" in result, f"deletion via empty new_string should work, got: {result!r}"
    assert f.read_text() == "world\n"


def test_edit_file_different_old_new_still_works(tmp_path):
    """Regression guard: normal edit still succeeds."""
    f = tmp_path / "f.txt"
    f.write_text("foo bar\n")
    result = tool_edit_file(str(f), "foo", "baz")
    assert "[OK]" in result
    assert f.read_text() == "baz bar\n"
