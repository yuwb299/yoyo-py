"""Tests for tool_read_file with non-positive limit/offset.

LLMs sometimes pass limit=0 or negative values. The non-incremental path
produced broken headers like "[Showing lines 1-0 of 3]" and "[Showing lines
1--3 of 3]" (double minus from negative end). Non-positive limit should be
treated as a sensible default (read something useful), and the header must
always show a valid range.
"""

from src.tools import tool_read_file


def test_read_file_limit_zero_uses_default(tmp_path):
    """limit=0 should not produce an empty/nonsensical range."""
    f = tmp_path / "f.txt"
    f.write_text("a\nb\nc\n")
    result = tool_read_file(str(f), limit=0)
    # Should contain actual content, not "lines 1-0"
    assert "1-0" not in result, f"limit=0 produced bad range: {result!r}"
    assert "a" in result, f"limit=0 should still read content: {result!r}"


def test_read_file_limit_negative_uses_default(tmp_path):
    """limit=-3 should not produce 'lines 1--3' (double minus)."""
    f = tmp_path / "f.txt"
    f.write_text("a\nb\nc\nd\ne\n")
    result = tool_read_file(str(f), limit=-3)
    assert "1--3" not in result, f"negative limit produced bad range: {result!r}"
    assert "--" not in result.split("\n")[0], (
        f"negative limit produced double-minus in header: {result!r}"
    )


def test_read_file_offset_zero_treated_as_one(tmp_path):
    """offset=0 should behave like offset=1 (read from start)."""
    f = tmp_path / "f.txt"
    f.write_text("first\nsecond\nthird\n")
    result = tool_read_file(str(f), offset=0)
    assert "first" in result, f"offset=0 should read from start: {result!r}"


def test_read_file_offset_negative_treated_as_one(tmp_path):
    """Negative offset should be clamped to 1, not crash or read garbage."""
    f = tmp_path / "f.txt"
    f.write_text("first\nsecond\n")
    result = tool_read_file(str(f), offset=-10)
    assert "first" in result, f"negative offset should clamp to start: {result!r}"


def test_read_file_limit_one_works(tmp_path):
    """Regression guard: limit=1 (smallest valid value) still works."""
    f = tmp_path / "f.txt"
    f.write_text("a\nb\nc\n")
    result = tool_read_file(str(f), limit=1)
    assert "a" in result
    assert "b" not in result.split("\n")  # only one line of content
