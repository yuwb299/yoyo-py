"""Tests for _apply_total_match_cap with context lines.

rg's --context emits context lines using a '-' separator (e.g. `path-5-line`)
while match lines use ':' (e.g. `path:5:line`). The previous cap counted ALL
output lines as "matches", so when context was present the truncation notice
reported context lines as omitted matches. It also reported a misleadingly
small omitted count when --max-count had already capped per-file matches at
the rg level.

These tests pin the behavior: only real match lines count toward the cap,
and the notice must not claim context lines are matches.
"""

from src.tools import _apply_total_match_cap


def test_cap_counts_only_match_lines_not_context():
    """With context, context lines must not be counted as omitted matches."""
    # 2 matches with 1 context line each (4 lines total).
    # max_results=2 should NOT truncate (2 matches <= 2).
    raw = "\n".join([
        "f.txt-1-before ctx",
        "f.txt:2:MATCH one",
        "f.txt-3-after ctx",
        "f.txt:5:MATCH two",
    ])
    result = _apply_total_match_cap(raw, max_results=2)
    # No truncation notice because match count (2) <= max_results (2)
    assert "omitted" not in result.lower(), (
        f"should not truncate when matches <= max_results, got:\n{result}"
    )
    assert "MATCH one" in result
    assert "MATCH two" in result


def test_cap_truncates_on_match_count_not_total_lines():
    """4 matches (with context) + max_results=2 → truncate after 2 matches."""
    raw = "\n".join([
        "f.txt:1:MATCH one",
        "f.txt-2-ctx",
        "f.txt:3:MATCH two",
        "f.txt-4-ctx",
        "f.txt:5:MATCH three",
        "f.txt-6-ctx",
        "f.txt:7:MATCH four",
    ])
    result = _apply_total_match_cap(raw, max_results=2)
    assert "MATCH one" in result
    assert "MATCH two" in result
    # Third+ matches must be dropped
    assert "MATCH three" not in result
    assert "MATCH four" not in result
    # Notice must report omitted MATCHES (2), not total lines (5)
    assert "omitted" in result.lower()


def test_no_context_still_caps_correctly():
    """Without context, every line is a match — original behavior preserved."""
    raw = "\n".join([f"f.txt:{i}:match {i}" for i in range(1, 6)])
    result = _apply_total_match_cap(raw, max_results=2)
    assert "match 1" in result
    assert "match 2" in result
    assert "match 3" not in result


def test_no_truncation_when_under_limit():
    """3 matches, max_results=10 → no notice."""
    raw = "\n".join([
        "f.txt:1:m1",
        "f.txt-2-ctx",
        "f.txt:3:m2",
    ])
    result = _apply_total_match_cap(raw, max_results=10)
    assert "omitted" not in result.lower()


def test_single_file_no_path_match_format():
    """rg omits the path for a single streamed file: 'NUM:content' / 'NUM-content'."""
    raw = "\n".join([
        "1-before",
        "2:MATCH",
        "3-after",
    ])
    # 1 match, max_results=5 → no truncation despite 3 total lines
    result = _apply_total_match_cap(raw, max_results=5)
    assert "omitted" not in result.lower(), (
        f"1 match should not be truncated by 2 context lines, got:\n{result}"
    )
    assert "MATCH" in result
