"""Tests for /last command — redisplay last assistant response."""

from src.repl import _find_last_assistant_response


class TestFindLastAssistantResponse:
    """Test the helper function that finds the last assistant text response."""

    def test_finds_last_assistant_text(self):
        """Should return the last assistant message with text content."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"},
            {"role": "assistant", "content": "I'm doing well!"},
        ]
        result = _find_last_assistant_response(messages)
        assert result == "I'm doing well!"

    def test_finds_last_assistant_before_tool_messages(self):
        """Should skip tool-call-only assistants and find the last one with text."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "tc1", "function": {"name": "read_file", "arguments": '{"path": "test.py"}'}}
            ]},
            {"role": "tool", "tool_call_id": "tc1", "content": "file contents"},
            {"role": "assistant", "content": "Here's the file contents"},
        ]
        result = _find_last_assistant_response(messages)
        assert result == "Here's the file contents"

    def test_returns_none_for_no_assistant(self):
        """Should return None if there's no assistant message."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ]
        result = _find_last_assistant_response(messages)
        assert result is None

    def test_returns_none_for_empty_conversation(self):
        """Should return None for empty message list."""
        result = _find_last_assistant_response([])
        assert result is None

    def test_skips_error_messages(self):
        """Should skip assistant messages that are error markers."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Good response"},
            {"role": "user", "content": "Another question"},
            {"role": "assistant", "content": "[error: rate limited]"},
        ]
        result = _find_last_assistant_response(messages)
        assert result == "Good response"

    def test_skips_interrupted_messages(self):
        """Should skip assistant messages that are just interruption markers."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Let me think about this...\n[interrupted]"},
            {"role": "user", "content": "Try again"},
            {"role": "assistant", "content": "Here's the answer!"},
        ]
        result = _find_last_assistant_response(messages)
        assert result == "Here's the answer!"

    def test_handles_tool_call_only_assistant(self):
        """Should return None if the last assistant only has tool calls and no text."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "tc1", "function": {"name": "bash", "arguments": '{"command": "ls"}'}}
            ]},
        ]
        result = _find_last_assistant_response(messages)
        # The assistant has no meaningful text — None or empty content
        assert result is None or result == ""
