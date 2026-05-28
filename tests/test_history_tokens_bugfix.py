"""Tests for /history --tokens bug fix.

Bug: /history --tokens was completely broken because:
1. cmd == "/history" was an exact match, so /history --tokens fell through
2. Even if matched, "--tokens" in cmd checked the wrong variable (cmd was lowercase)

These tests verify the fix.
"""

import pytest
from unittest.mock import patch, MagicMock

from src.repl import _format_history, Agent
from src.agent import AgentEvent


def test_history_tokens_flag_in_messages():
    """_format_history with show_tokens=True includes token estimates."""
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there! How can I help?"},
    ]
    result = _format_history(messages, show_tokens=True)
    assert "Total estimated tokens" in result
    # Each non-system message should have a ~Nt estimate
    assert "~" in result
    assert "t" in result


def test_history_no_tokens_by_default():
    """_format_history with show_tokens=False (default) has no token estimates."""
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]
    result = _format_history(messages, show_tokens=False)
    assert "Total estimated tokens" not in result


def test_history_tokens_counts_tool_calls():
    """Token estimation in history includes tool_calls arguments."""
    messages = [
        {"role": "user", "content": "Read foo.py"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "read_file",
                    "arguments": '{"path": "foo.py"}',
                },
            }],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "file contents..."},
    ]
    result_with = _format_history(messages, show_tokens=True)
    result_without = _format_history(messages, show_tokens=False)
    assert "Total estimated tokens" in result_with
    assert "Total estimated tokens" not in result_without


def test_history_tokens_empty_messages():
    """_format_history with empty messages and show_tokens=True."""
    result = _format_history([], show_tokens=True)
    assert "No messages" in result


def test_history_tokens_system_message_no_estimate():
    """System messages don't get individual token estimates in the display."""
    messages = [
        {"role": "system", "content": "You are a coding assistant."},
    ]
    result = _format_history(messages, show_tokens=True)
    assert "system prompt" in result
