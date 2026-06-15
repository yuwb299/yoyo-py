"""Tests for _read_file_incremental with non-positive limit/offset.

The main tool_read_file path clamps limit<1 to 500 and offset<1 to 1, with
a comment explaining why: limit=0 produced "[Showing lines 1-0 of N]" (empty
range) and limit=-3 produced "[Showing lines 1--3 of N]" (double-minus).

The incremental path (used for files >500KB with small ranges) is a separate
function with its OWN copy of the range logic but WITHOUT the clamp. Calling
it directly with limit=0 / limit=-3 reproduces the same broken headers. This
makes the function unsafe to call directly and fragile if the clamp location
in tool_read_file ever moves.

These tests pin the incremental path to the same clamping contract.
"""

from src.tools import _read_file_incremental


def _make_large_file(tmp_path):
    """Create a file >500KB so the incremental path's assumptions hold."""
    f = tmp_path / "big.txt"
    # ~42 bytes/line × 20000 lines ≈ 840KB
    f.write_text("\n".join(f"line {i} padding padding padding padding" for i in range(20000)))
    return f


def test_incremental_limit_zero_does_not_produce_empty_range(tmp_path):
    """limit=0 must not yield '[Showing lines 1-0 of N]'."""
    f = _make_large_file(tmp_path)
    result = _read_file_incremental(f, offset=1, limit=0, path_str=str(f))
    assert "1-0" not in result, f"limit=0 produced bad range: {result[:120]!r}"


def test_incremental_limit_negative_no_double_minus(tmp_path):
    """limit=-3 must not yield '[Showing lines 1--3 of N]'."""
    f = _make_large_file(tmp_path)
    result = _read_file_incremental(f, offset=1, limit=-3, path_str=str(f))
    # Header is the first line; it must not contain a double-minus range.
    assert "1--3" not in result, f"negative limit produced bad range: {result[:120]!r}"


def test_incremental_offset_zero_reads_from_start(tmp_path):
    """offset=0 should behave like offset=1 (read from the start)."""
    f = _make_large_file(tmp_path)
    result = _read_file_incremental(f, offset=0, limit=3, path_str=str(f))
    assert "line 0" in result, f"offset=0 should read from start: {result[:120]!r}"


def test_incremental_returns_real_content_for_valid_range(tmp_path):
    """Regression guard: a normal small range still returns the right lines."""
    f = _make_large_file(tmp_path)
    result = _read_file_incremental(f, offset=1, limit=3, path_str=str(f))
    assert "line 0" in result
    assert "line 1" in result
    assert "line 2" in result
    assert "line 3" not in result  # only 3 lines requested
