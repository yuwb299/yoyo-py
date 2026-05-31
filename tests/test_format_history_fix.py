"""Tests for _format_history edge cases — crash bugs with malformed tool_calls."""

import pytest
from src.repl import _format_history


def test_format_history_tool_calls_missing_name():
    """tool_calls with function dict but no name key should not crash."""
    messages = [
        {"role": "assistant", "tool_calls": [{"function": {}}], "content": None},
    ]
    result = _format_history(messages)
    assert "assistant" in result


def test_format_history_tool_calls_empty_function():
    """tool_calls with empty function dict should handle gracefully."""
    messages = [
        {"role": "assistant", "tool_calls": [{"id": "call_123", "function": {"arguments": "{}"}}], "content": None},
    ]
    result = _format_history(messages)
    assert "assistant" in result


def test_format_history_tool_calls_partial_function():
    """tool_calls with only arguments but no name should not crash."""
    messages = [
        {"role": "assistant", "tool_calls": [{"id": "call_456", "function": {"arguments": '{"path": "/foo"}'}}], "content": "thinking..."},
    ]
    result = _format_history(messages)
    assert "assistant" in result
    assert "thinking..." in result


def test_format_history_normal_tool_calls_still_work():
    """Normal tool_calls with name present still works correctly."""
    messages = [
        {"role": "assistant", "tool_calls": [
            {"id": "call_789", "function": {"name": "bash", "arguments": '{"command": "ls"}'}}
        ], "content": None},
    ]
    result = _format_history(messages)
    assert "bash" in result


def test_format_history_tool_calls_with_content():
    """Tool calls with both text content and tool calls."""
    messages = [
        {"role": "assistant", "tool_calls": [
            {"id": "call_abc", "function": {"name": "read_file", "arguments": '{"path": "/test"}'}}
        ], "content": "Let me read that file."},
    ]
    result = _format_history(messages)
    assert "read_file" in result
    assert "Let me read that file." in result


def test_format_history_mixed_good_and_bad_tool_calls():
    """Mix of well-formed and malformed tool_calls entries."""
    messages = [
        {"role": "assistant", "tool_calls": [
            {"id": "call_1", "function": {"name": "bash", "arguments": '{"command": "ls"}'}},
            {"id": "call_2", "function": {}},
        ], "content": None},
    ]
    # Should not crash — gracefully handles both
    result = _format_history(messages)
    assert "bash" in result
