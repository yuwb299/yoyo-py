"""Tests for /system command to view current system prompt."""

from src.repl import _format_system_prompt_display


class TestSystemPromptDisplay:
    """Test the system prompt display formatter."""

    def test_shows_system_prompt_content(self):
        messages = [
            {"role": "system", "content": "You are a coding assistant."},
            {"role": "user", "content": "hello"},
        ]
        result = _format_system_prompt_display(messages)
        assert "You are a coding assistant." in result

    def test_no_system_message(self):
        messages = [
            {"role": "user", "content": "hello"},
        ]
        result = _format_system_prompt_display(messages)
        assert "No system prompt" in result

    def test_empty_messages(self):
        result = _format_system_prompt_display([])
        assert "No system prompt" in result

    def test_shows_header(self):
        messages = [
            {"role": "system", "content": "test prompt"},
        ]
        result = _format_system_prompt_display(messages)
        assert "System Prompt" in result

    def test_shows_line_count(self):
        long_prompt = "\n".join([f"Line {i}" for i in range(20)])
        messages = [
            {"role": "system", "content": long_prompt},
        ]
        result = _format_system_prompt_display(messages)
        assert "20" in result  # Should mention line count

    def test_truncates_very_long_prompts(self):
        # A very long prompt should be truncated in the display
        long_prompt = "x" * 5000
        messages = [
            {"role": "system", "content": long_prompt},
        ]
        result = _format_system_prompt_display(messages)
        # Should show a truncation indicator
        assert "truncated" in result.lower() or len(result) < 6000
