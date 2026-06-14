"""Tests for tool_search max_results enforcement.

max_results should bound the TOTAL number of matching lines returned,
not the per-file count (which is what rg --max-count does).

Before the fix, searching 3 files with max_results=2 returned up to 6
results (2 per file). After the fix, exactly 2 lines are returned and a
truncation notice tells the LLM there were more matches.
"""

from src.tools import tool_search


def test_max_results_caps_total_matches_across_files(tmp_path):
    """3 files × 5 matches each, max_results=2 → at most 2 matching lines total."""
    for i in range(3):
        (tmp_path / f"f{i}.txt").write_text("\n".join(f"match line {j}" for j in range(5)) + "\n")

    result = tool_search("match", path=str(tmp_path), max_results=2)

    # Count the actual match lines (rg format: path:linenum:content, no leading dash)
    match_lines = [
        line for line in result.splitlines()
        if line.strip() and ":match" in line and "-match" not in line
    ]
    assert len(match_lines) <= 2, (
        f"max_results=2 should return at most 2 matches total, got {len(match_lines)}:\n{result}"
    )


def test_max_results_reports_truncation(tmp_path):
    """When results are truncated, the LLM must be told so it can re-search if needed."""
    for i in range(3):
        (tmp_path / f"f{i}.txt").write_text("\n".join(f"match line {j}" for j in range(5)) + "\n")

    result = tool_search("match", path=str(tmp_path), max_results=2)

    # Should mention that more results exist
    assert "more" in result.lower() or "truncat" in result.lower() or "..." in result, (
        f"truncated output should warn about more matches, got:\n{result}"
    )


def test_max_results_no_truncation_notice_when_under_limit(tmp_path):
    """When matches fit within max_results, no truncation notice is shown."""
    (tmp_path / "f.txt").write_text("only one match here\n")
    result = tool_search("match", path=str(tmp_path), max_results=10)
    assert "more matches" not in result.lower(), (
        f"no truncation notice expected, got:\n{result}"
    )


def test_max_results_one_returns_single_match(tmp_path):
    """max_results=1 returns exactly one match line."""
    (tmp_path / "a.txt").write_text("match\nmatch\nmatch\n")
    (tmp_path / "b.txt").write_text("match\nmatch\n")
    result = tool_search("match", path=str(tmp_path), max_results=1)
    match_lines = [
        line for line in result.splitlines()
        if line.strip() and ":match" in line and "-match" not in line
    ]
    assert len(match_lines) == 1, (
        f"expected exactly 1 match, got {len(match_lines)}:\n{result}"
    )
