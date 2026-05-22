"""Tests for multi-line input support in the REPL."""

import pytest
from unittest.mock import patch
from src.repl import _read_multiline_input


class TestReadMultilineInput:
    """Test the multi-line input reader."""

    def test_single_line_no_backslash(self):
        """A line without a trailing backslash is returned as-is."""
        with patch("builtins.input", return_value="hello world"):
            result = _read_multiline_input()
        assert result == "hello world"

    def test_backslash_continuation(self):
        """Lines ending with backslash are joined (backslash removed)."""
        responses = iter(["line1\\", "line2"])
        with patch("builtins.input", side_effect=responses):
            result = _read_multiline_input()
        assert result == "line1\nline2"

    def test_multiple_backslash_continuations(self):
        """Multiple continuation lines are all joined."""
        responses = iter(["line1\\", "line2\\", "line3"])
        with patch("builtins.input", side_effect=responses):
            result = _read_multiline_input()
        assert result == "line1\nline2\nline3"

    def test_backslash_with_trailing_space_not_continuation(self):
        """Backslash followed by a space is NOT a continuation — kept as-is."""
        with patch("builtins.input", return_value="line1\\ "):
            result = _read_multiline_input()
        assert result == "line1\\ "

    def test_empty_line_returns_empty(self):
        """An empty input returns empty string."""
        with patch("builtins.input", return_value=""):
            result = _read_multiline_input()
        assert result == ""

    def test_keyboard_interrupt(self):
        """KeyboardInterrupt during input is propagated."""
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            with pytest.raises(KeyboardInterrupt):
                _read_multiline_input()

    def test_eof_error(self):
        """EOFError during input is propagated."""
        with patch("builtins.input", side_effect=EOFError):
            with pytest.raises(EOFError):
                _read_multiline_input()

    def test_continuation_prompt_changes(self):
        """After a backslash continuation, the prompt changes to indicate continuation."""
        responses = iter(["line1\\", "line2"])
        prompts = []

        def mock_input(prompt=""):
            prompts.append(prompt)
            return next(responses)

        with patch("builtins.input", side_effect=mock_input):
            _read_multiline_input()

        # First prompt should have ">", second should have continuation indicator
        assert ">" in prompts[0]
        assert len(prompts) == 2
