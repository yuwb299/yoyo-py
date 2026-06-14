"""Tests for clamping numeric tool arguments that the LLM may send out of range.

The LLM sometimes sends nonsensical values like max_results=-5 or
max_results=0. Left unchecked these produce confusing downstream behavior:

- tool_search with max_results=-5 → rg errors: "value is not a valid number"
- tool_search with max_results=0  → rg runs with no limit but reports
  "[No matches found]" when there are matches (misleading)
- tool_glob with max_results=0    → reports "[No files found matching pattern]"
  even when files exist (misleading)
- tool_list_files with negative max_depth → produces "[Empty directory]"
  message for a populated directory (misleading)

Each tool should clamp numeric args to a sensible minimum (typically >=1)
so the tool does something reasonable instead of erroring or lying.
"""

import os

from src.tools import tool_search, tool_glob, tool_list_files


# ── tool_search: max_results clamping ──────────────────────────────────────

def test_search_negative_max_results_does_not_error(tmp_path):
    """max_results=-5 must not be passed to rg, which errors on negative."""
    (tmp_path / "a.txt").write_text("hello world\n")
    result = tool_search("hello", path=str(tmp_path), max_results=-5)
    # Should find the match, not surface an rg parse error
    assert "hello world" in result, f"expected match, got: {result!r}"
    assert "value is not a valid number" not in result, (
        f"negative max_results leaked to rg, got: {result!r}"
    )


def test_search_zero_max_results_does_not_lie_about_no_matches(tmp_path):
    """max_results=0 must not report 'No matches found' when matches exist.

    rg --max-count 0 means unlimited, but the original code reported
    '[No matches found]' on the empty output. Clamping to >=1 fixes this.
    """
    (tmp_path / "a.txt").write_text("hello world\n")
    result = tool_search("hello", path=str(tmp_path), max_results=0)
    assert "hello world" in result, (
        f"max_results=0 should still find matches, got: {result!r}"
    )
    assert "No matches found" not in result, (
        f"should not falsely report no matches, got: {result!r}"
    )


def test_search_positive_max_results_still_truncates(tmp_path):
    """Regression: normal max_results still limits the count."""
    (tmp_path / "a.txt").write_text("line\nline\nline\nline\nline\n")
    result = tool_search("line", path=str(tmp_path), max_results=2)
    # Should have at most 2 matching lines (after the header line)
    match_lines = [l for l in result.splitlines() if "line" in l and "a.txt" in l]
    assert len(match_lines) <= 2


# ── tool_glob: max_results clamping ────────────────────────────────────────

def test_glob_zero_max_results_does_not_lie_about_no_files(tmp_path):
    """max_results=0 must not report 'No files found' when files exist."""
    (tmp_path / "a.py").write_text("x\n")
    (tmp_path / "b.py").write_text("x\n")
    result = tool_glob("*.py", path=str(tmp_path), max_results=0)
    assert "a.py" in result, f"max_results=0 should still find files, got: {result!r}"
    assert "No files found" not in result, (
        f"should not falsely report no files, got: {result!r}"
    )


def test_glob_negative_max_results_finds_files(tmp_path):
    """max_results=-5 must be clamped, not produce empty results."""
    (tmp_path / "a.py").write_text("x\n")
    result = tool_glob("*.py", path=str(tmp_path), max_results=-5)
    assert "a.py" in result, f"negative max_results should still find files, got: {result!r}"


# ── tool_list_files: max_depth clamping ────────────────────────────────────

def test_list_files_negative_max_depth_does_not_report_empty(tmp_path):
    """Negative max_depth must not report '[Empty directory]' for a populated dir.

    find -maxdepth -1 errors; os.walk fallback computes depth>=max_depth which
    is always true for negative values, filtering out everything. The result
    '[Empty directory]' is misleading because the directory isn't empty.
    """
    (tmp_path / "a.txt").write_text("x\n")
    (tmp_path / "b.txt").write_text("x\n")
    result = tool_list_files(str(tmp_path), max_depth=-1)
    assert "a.txt" in result, (
        f"negative max_depth should still list files, got: {result!r}"
    )
    assert "Empty directory" not in result, (
        f"populated dir must not be reported as empty, got: {result!r}"
    )


def test_list_files_zero_max_depth_lists_top_level(tmp_path):
    """max_depth=0 should behave like listing only the top-level directory.

    Convention: treat <=0 as 'no depth limit' (same as None) to avoid the
    confusing empty-result behavior.
    """
    (tmp_path / "a.txt").write_text("x\n")
    result = tool_list_files(str(tmp_path), max_depth=0)
    assert "a.txt" in result, f"max_depth=0 should list top-level files, got: {result!r}"


def test_list_files_glob_no_match_not_reported_as_empty(tmp_path):
    """When a glob filter excludes everything, do not say '[Empty directory]'.

    The directory has files — the glob just didn't match any. Reporting
    '[Empty directory]' is factually wrong and confuses the LLM into
    thinking the directory has nothing in it.
    """
    (tmp_path / "a.py").write_text("x\n")
    (tmp_path / "b.py").write_text("x\n")
    result = tool_list_files(str(tmp_path), glob_pattern="*.nonexistent")
    assert "Empty directory" not in result, (
        f"glob no-match must not be reported as empty dir, got: {result!r}"
    )
    # Should mention that the filter matched nothing, or report no files found
    # — but it must NOT claim the directory is empty.
    assert "no files" in result.lower() or "no match" in result.lower() or "0 files" in result, (
        f"should clarify it's a filter issue, got: {result!r}"
    )


def test_list_files_actually_empty_directory_still_reports_empty(tmp_path):
    """Regression: a truly empty directory should still report as empty."""
    result = tool_list_files(str(tmp_path))
    assert "empty" in result.lower(), f"empty dir should be reported as empty, got: {result!r}"


def test_list_files_positive_max_depth_still_filters(tmp_path):
    """Regression: a normal max_depth still limits depth."""
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "deep.txt").write_text("x\n")
    (tmp_path / "top.txt").write_text("x\n")
    # max_depth=1 should include top.txt but exclude sub/deep.txt
    result = tool_list_files(str(tmp_path), max_depth=1)
    assert "top.txt" in result
    assert "deep.txt" not in result
