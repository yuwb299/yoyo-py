"""Tests for /export command — export conversation as markdown."""

import json
import os
import tempfile

from src.repl import _export_conversation_markdown


def test_export_basic_conversation():
    """Export a simple user/assistant conversation."""
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello!"},
        {"role": "assistant", "content": "Hi there! How can I help?"},
    ]

    result = _export_conversation_markdown(messages, model="glm-5")
    assert "# Conversation Export" in result
    assert "glm-5" in result
    assert "Hello!" in result
    assert "Hi there!" in result
    assert "## User" in result
    assert "## Assistant" in result


def test_export_with_tool_calls():
    """Export conversation including tool calls."""
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "read the file"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "call_1", "type": "function", "function": {"name": "read_file", "arguments": '{"path": "test.py"}'}},
        ]},
        {"role": "tool", "tool_call_id": "call_1", "content": "file contents here"},
        {"role": "assistant", "content": "Here's the file."},
    ]

    result = _export_conversation_markdown(messages, model="glm-5")
    assert "read_file" in result
    assert "test.py" in result
    assert "file contents here" in result
    assert "Here's the file." in result


def test_export_excludes_system_prompt():
    """Export should skip system prompt by default."""
    messages = [
        {"role": "system", "content": "Secret system instructions"},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi"},
    ]

    result = _export_conversation_markdown(messages, model="glm-5")
    assert "Secret system instructions" not in result


def test_export_includes_system_prompt_when_requested():
    """Export should include system prompt when include_system=True."""
    messages = [
        {"role": "system", "content": "Secret system instructions"},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi"},
    ]

    result = _export_conversation_markdown(messages, model="glm-5", include_system=True)
    assert "Secret system instructions" in result


def test_export_empty_conversation():
    """Export handles empty conversation."""
    result = _export_conversation_markdown([], model="glm-5")
    assert "# Conversation Export" in result
    assert "glm-5" in result


def test_export_truncates_long_tool_output():
    """Export should truncate very long tool outputs."""
    long_content = "x" * 5000
    messages = [
        {"role": "tool", "tool_call_id": "1", "content": long_content},
    ]

    result = _export_conversation_markdown(messages, model="glm-5")
    # Should be truncated to ~500 chars + truncation notice
    assert len(result) < 5000
    assert "truncated" in result.lower()
