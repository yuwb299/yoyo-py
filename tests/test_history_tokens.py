"""Test /history command with token estimation."""

import pytest

from src.repl import _format_history
from src.agent import Agent


def test_empty_history():
    """Empty message list returns appropriate message."""
    result = _format_history([])
    assert "No messages" in result


def test_system_message():
    """System messages are summarized, not shown in full."""
    messages = [{"role": "system", "content": "You are a helpful assistant."}]
    result = _format_history(messages)
    assert "system prompt" in result


def test_user_assistant_messages():
    """User and assistant messages are shown with previews."""
    messages = [
        {"role": "user", "content": "Hello, how are you?"},
        {"role": "assistant", "content": "I'm doing well, thanks for asking!"},
    ]
    result = _format_history(messages)
    assert "user" in result
    assert "assistant" in result
    assert "Hello, how are you?" in result


def test_tool_call_messages():
    """Assistant messages with tool_calls show the tool names."""
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "bash", "arguments": '{"command": "ls"}'},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": "file1.txt\nfile2.txt",
        },
    ]
    result = _format_history(messages)
    assert "bash" in result
    assert "tool" in result.lower()


def test_token_estimation_in_history():
    """History shows estimated token count when show_tokens=True."""
    long_content = "x" * 300  # ~100 tokens
    messages = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": long_content},
    ]
    result = _format_history(messages, show_tokens=True)
    # Should include token estimate
    assert "token" in result.lower()


def test_no_token_estimation_by_default():
    """By default, history does not show token estimates."""
    messages = [
        {"role": "user", "content": "Hello"},
    ]
    result = _format_history(messages)
    # Should NOT include token estimation
    assert "~" not in result or "token" not in result.lower()


def test_truncated_preview():
    """Long messages are truncated in preview."""
    long_text = "A" * 200
    messages = [{"role": "user", "content": long_text}]
    result = _format_history(messages)
    assert "..." in result
