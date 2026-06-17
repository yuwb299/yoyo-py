"""Tests for _run_grep context-line handling.

Background: /grep with -C N printed overlapping context lines twice when
matches were adjacent (the context for match A included match B's line,
which then appeared again as its own match). The match-count header also
counted context lines as if they were matches. Both are fixed by:
  - tracking displayed (path, line_num) keys to dedupe,
  - counting only real matches (not context lines) in the header.
"""

import os
import tempfile

import pytest

from src.repl import _run_grep


@pytest.fixture
def grep_cwd(tmp_path, monkeypatch):
    """Create a temp dir with adjacent matches and chdir into it."""
    (tmp_path / "f.txt").write_text("line1\nMATCH\nMATCH\nline4\n")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _strip_ansi(s: str) -> str:
    import re

    return re.sub(r"\x1b\[[0-9;]*m", "", s)


def test_grep_context_does_not_duplicate_adjacent_match(grep_cwd):
    # The line "f.txt:3:MATCH" is BOTH a real match AND a context line for
    # the match at line 2. Before the fix it printed twice; it should print
    # exactly once.
    out = _strip_ansi(_run_grep("MATCH -C 1"))
    assert out.count("f.txt:3") == 1, f"line 3 duplicated:\n{out}"


def test_grep_match_count_excludes_context_lines(grep_cwd):
    # 2 real matches; header should say "2 matches", not 6 (2 matches + 4 ctx).
    out = _strip_ansi(_run_grep("MATCH -C 1"))
    assert "2 matches" in out, f"match count wrong:\n{out}"


def test_grep_still_shows_context_lines(grep_cwd):
    # Positive control: context lines should still appear (deduped).
    out = _strip_ansi(_run_grep("MATCH -C 1"))
    assert "f.txt:1" in out  # context line before first match
    assert "f.txt:4" in out  # context line after last match


def test_grep_no_context_no_duplication(grep_cwd):
    # Without -C, no context lines, two matches, both shown once.
    out = _strip_ansi(_run_grep("MATCH"))
    assert "2 matches" in out
    assert out.count("f.txt:2") == 1
    assert out.count("f.txt:3") == 1


def test_grep_context_no_overflow_beyond_results(grep_cwd):
    # Context lines must not be counted toward the max_results truncation.
    # With max_results=50 and a tiny file this won't truncate, but ensure the
    # "truncated" footer does not spuriously appear.
    out = _strip_ansi(_run_grep("MATCH -C 1"))
    assert "truncated" not in out.lower()
