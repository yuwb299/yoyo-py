"""Tests for tool_search edge case: empty/whitespace search patterns.

An empty pattern passed to ripgrep matches EVERY line in every file (rg treats
'' as a match-all regex). This dumps entire file contents into the conversation,
wasting thousands of context tokens — and it is never what the caller intends.
We should reject empty/whitespace-only patterns with a clear error message.

Whitespace-only patterns ('   ') are equally meaningless as a search term and
should be rejected for the same reason.
"""

from src.tools import tool_search


class TestSearchEmptyPattern:
    """Empty or whitespace-only patterns should be rejected, not treated as match-all."""

    def test_empty_pattern_rejected(self, tmp_path):
        """Empty string pattern must not dump entire file contents."""
        (tmp_path / "f.txt").write_text("line one\nline two\nline three\n")
        result = tool_search("", path=str(tmp_path))
        assert result.startswith("[ERROR]"), f"expected error, got: {result!r}"
        # Must NOT return all the file contents (the bug behavior)
        assert "line one" not in result, (
            f"empty pattern should not match all lines, got: {result!r}"
        )

    def test_whitespace_pattern_rejected(self, tmp_path):
        """Whitespace-only pattern is meaningless as a search term."""
        (tmp_path / "f.txt").write_text("line one\nline two\n")
        result = tool_search("   ", path=str(tmp_path))
        assert result.startswith("[ERROR]"), f"expected error, got: {result!r}"
        assert "line one" not in result, (
            f"whitespace pattern should not match all lines, got: {result!r}"
        )

    def test_error_message_mentions_pattern(self, tmp_path):
        """Error message should explain that the pattern is empty."""
        (tmp_path / "f.txt").write_text("data\n")
        result = tool_search("", path=str(tmp_path))
        assert "[ERROR]" in result
        # Message should hint at the problem (empty pattern)
        lowered = result.lower()
        assert "empty" in lowered or "pattern" in lowered, (
            f"error should explain the empty-pattern problem, got: {result!r}"
        )

    def test_normal_pattern_still_works(self, tmp_path):
        """Regression guard: a normal pattern still finds matches."""
        (tmp_path / "f.txt").write_text("hello world\nfoo bar\n")
        result = tool_search("foo", path=str(tmp_path))
        assert "foo bar" in result
