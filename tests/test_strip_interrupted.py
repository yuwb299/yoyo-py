"""Tests for _strip_interrupted_marker helper."""

from src.repl import _strip_interrupted_marker


class TestStripInterruptedMarker:
    """Test stripping the [interrupted] suffix from assistant messages."""

    def test_strips_trailing_interrupted(self):
        assert _strip_interrupted_marker("Hello world\n[interrupted]") == "Hello world"

    def test_no_marker_returns_unchanged(self):
        assert _strip_interrupted_marker("Hello world") == "Hello world"

    def test_only_marker_returns_empty(self):
        assert _strip_interrupted_marker("[interrupted]") == ""

    def test_marker_in_middle_is_not_stripped(self):
        # Edge case: "[interrupted]" in the middle of content should stay
        assert _strip_interrupted_marker("before [interrupted] after") == "before [interrupted] after"

    def test_empty_string(self):
        assert _strip_interrupted_marker("") == ""

    def test_strips_trailing_whitespace_after_removal(self):
        assert _strip_interrupted_marker("Hello  \n[interrupted]") == "Hello"
