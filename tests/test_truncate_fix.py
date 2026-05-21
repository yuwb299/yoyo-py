"""Tests for the _truncate UTF-8 fix — ensuring multi-byte characters aren't garbled."""

from src.tools import _truncate


class TestTruncateUTF8:
    def test_truncate_preserves_multibyte_characters(self):
        """Truncation should not split multi-byte UTF-8 characters."""
        # Each 你 is 3 bytes in UTF-8. If we truncate at a byte boundary
        # that falls in the middle of a character, we should not get garbled output.
        text = "你好世界" * 100  # 12 bytes per repetition = 1200 bytes
        result = _truncate(text, 100)
        assert isinstance(result, str)
        # Should not contain replacement characters from broken UTF-8
        assert "\ufffd" not in result

    def test_truncate_exact_multibyte_boundary(self):
        """Truncation at exact multibyte character boundary should be clean."""
        # 你好 = 6 bytes
        text = "你好" * 50  # 300 bytes
        result = _truncate(text, 297)  # 297 = 99 * 3, should cut cleanly
        assert isinstance(result, str)
        # Should not have replacement character
        assert "\ufffd" not in result

    def test_truncate_ascii_still_works(self):
        """ASCII text truncation should work exactly as before."""
        text = "x" * 200
        result = _truncate(text, 100)
        assert "truncated" in result
        assert len(result) < 200

    def test_truncate_mixed_content(self):
        """Mixed ASCII and CJK content should truncate cleanly."""
        text = "Hello 你好 " * 100  # Mixed content
        result = _truncate(text, 200)
        assert isinstance(result, str)
        assert "\ufffd" not in result

    def test_truncate_short_text_unchanged(self):
        """Text under the limit should be returned unchanged."""
        text = "你好世界"
        result = _truncate(text, 50000)
        assert result == text
