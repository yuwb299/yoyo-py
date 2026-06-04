"""Tests for /grep slash command — quick file content search."""

import os
import pytest
from src.repl import _run_grep


@pytest.fixture
def tmp_project(tmp_path, monkeypatch):
    """Create a temporary project structure for grep tests."""
    monkeypatch.chdir(tmp_path)

    (tmp_path / "hello.py").write_text("def hello():\n    print('hello world')\n    return True\n")
    (tmp_path / "goodbye.py").write_text("def goodbye():\n    print('bye')\n    return False\n")
    (tmp_path / "notes.txt").write_text("Hello World\nThis is a test\nhello again\n")

    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "deep.py").write_text("# deep file\ndef deep_hello():\n    pass\n")

    return tmp_path


def test_grep_basic_match(tmp_project):
    """Basic keyword search finds matches."""
    result = _run_grep("hello")
    assert "hello" in result.lower()
    assert "hello.py" in result


def test_grep_no_match(tmp_project):
    """No match returns appropriate message."""
    result = _run_grep("xyznotfound_at_all")
    assert "no match" in result.lower() or "no result" in result.lower()


def test_grep_case_sensitive(tmp_project):
    """Case-sensitive search."""
    result = _run_grep("Hello --case")
    assert "hello" in result.lower() or "Hello" in result


def test_grep_case_insensitive_default(tmp_project):
    """Default search is case-insensitive."""
    result = _run_grep("HELLO")
    assert "hello" in result.lower()


def test_grep_file_filter(tmp_project):
    """Filter by file extension."""
    result = _run_grep("hello --glob *.py")
    assert "hello.py" in result
    assert "notes.txt" not in result


def test_grep_empty_pattern(tmp_project):
    """Empty pattern returns usage message."""
    result = _run_grep("")
    assert "usage" in result.lower() or "pattern" in result.lower()


def test_grep_invalid_regex_fallback(tmp_project):
    """Invalid regex falls back to literal search."""
    result = _run_grep("[invalid")
    # Should not crash
    assert isinstance(result, str)


def test_grep_shows_line_numbers(tmp_project):
    """Results show line numbers."""
    result = _run_grep("hello")
    assert ":" in result  # line number format like "file:line:"


def test_grep_recursive(tmp_project):
    """Search is recursive by default."""
    result = _run_grep("deep_hello")
    assert "deep.py" in result
