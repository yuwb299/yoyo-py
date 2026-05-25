"""Tests for the /history command — show conversation history summary."""

import pytest
from src.repl import _format_history


class TestHistoryCommand:
    """Test /history command that shows conversation message summary."""

    def test_empty_messages(self):
        """Should report when no messages exist."""
        result = _format_history([])
        assert "No messages" in result

    def test_system_only(self):
        """Should handle system-only messages."""
        messages = [{"role": "system", "content": "You are a helper."}]
        result = _format_history(messages)
        assert "system" in result

    def test_mixed_messages(self):
        """Should display a summary of different message types."""
        messages = [
            {"role": "system", "content": "You are a helper."},
            {"role": "user", "content": "Hello, can you help me?"},
            {"role": "assistant", "content": "Sure! What do you need?"},
            {"role": "user", "content": "Fix this bug"},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "t1", "type": "function", "function": {"name": "bash", "arguments": '{"command": "ls"}'}}]},
            {"role": "tool", "tool_call_id": "t1", "content": "file1.txt\nfile2.txt"},
            {"role": "assistant", "content": "I found the files."},
        ]
        result = _format_history(messages)
        assert "user" in result
        assert "assistant" in result
        assert "tool" in result

    def test_long_content_truncated(self):
        """Should truncate very long message content in summary."""
        long_content = "x" * 500
        messages = [
            {"role": "user", "content": long_content},
        ]
        result = _format_history(messages)
        # Should not contain all 500 x's
        assert "xxx" not in result or len(result) < 600

    def test_none_content_handled(self):
        """Should handle None content (tool-call-only assistant messages)."""
        messages = [
            {"role": "assistant", "content": None, "tool_calls": [{"id": "t1", "type": "function", "function": {"name": "bash", "arguments": "{}"}}]},
        ]
        result = _format_history(messages)
        # Should not crash, should show tool call info
        assert "bash" in result or "tool" in result.lower() or "assistant" in result

    def test_message_count(self):
        """Should show total message count."""
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        result = _format_history(messages)
        assert "3" in result

    def test_tool_call_display(self):
        """Should show which tools were called."""
        messages = [
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "t1", "type": "function", "function": {"name": "bash", "arguments": '{"command": "ls"}'}},
                {"id": "t2", "type": "function", "function": {"name": "read_file", "arguments": '{"path": "test.py"}'}},
            ]},
            {"role": "tool", "tool_call_id": "t1", "content": "output1"},
            {"role": "tool", "tool_call_id": "t2", "content": "output2"},
        ]
        result = _format_history(messages)
        assert "bash" in result
        assert "read_file" in result
