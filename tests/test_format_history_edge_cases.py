"""Tests for _format_history edge cases — safe dict access for tool_calls."""

from src.repl import _format_history


class TestFormatHistoryEdgeCases:
    """Tests for _format_history with malformed or edge-case tool_calls."""

    def test_tool_calls_with_none_function(self):
        """Tool call with function=None should not crash."""
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "type": "function", "function": None},
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "result"},
        ]
        # Should not crash
        result = _format_history(messages)
        assert "assistant" in result

    def test_tool_calls_with_missing_function_key(self):
        """Tool call without function key should not crash."""
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "type": "function"},
                ],
            },
        ]
        result = _format_history(messages)
        assert "assistant" in result

    def test_tool_calls_with_function_not_dict(self):
        """Tool call where function is a string should not crash."""
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "type": "function", "function": "not_a_dict"},
                ],
            },
        ]
        result = _format_history(messages)
        assert "assistant" in result

    def test_tool_calls_with_empty_function(self):
        """Tool call with empty function dict should show unknown."""
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "type": "function", "function": {}},
                ],
            },
        ]
        result = _format_history(messages)
        assert "?" in result

    def test_tool_calls_with_name_in_function(self):
        """Normal tool call should show the tool name."""
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "type": "function", "function": {"name": "bash", "arguments": "{}"}},
                ],
            },
        ]
        result = _format_history(messages)
        assert "bash" in result

    def test_tool_message_with_none_content(self):
        """Tool message with None content should not crash."""
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "type": "function", "function": {"name": "bash", "arguments": "{}"}},
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": None},
        ]
        result = _format_history(messages)
        assert "tool" in result
