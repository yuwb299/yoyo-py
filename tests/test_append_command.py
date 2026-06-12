"""Tests for /append command — inject messages without triggering agent response.

The /append command lets users add context to the conversation (paste error
messages, add notes, include file contents) without triggering an agent
response. This is useful when building up context before asking a question.
"""
import pytest
from unittest.mock import MagicMock


def test_append_basic():
    """Basic /append should add a user message without agent response."""
    from src.repl import _handle_append_command

    messages = []
    result = _handle_append_command("This is a note", messages)

    assert result is not None
    assert "appended" in result.lower() or "added" in result.lower()
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "This is a note"


def test_append_empty():
    """Empty /append should show usage hint."""
    from src.repl import _handle_append_command

    messages = []
    result = _handle_append_command("", messages)

    assert len(messages) == 0
    assert "usage" in result.lower() or "usage" in result


def test_append_multiline():
    """Append should handle multiline content."""
    from src.repl import _handle_append_command

    messages = []
    multiline = "line 1\nline 2\nline 3"
    result = _handle_append_command(multiline, messages)

    assert len(messages) == 1
    assert messages[0]["content"] == multiline


def test_append_preserves_existing():
    """Append should not touch existing messages."""
    from src.repl import _handle_append_command

    messages = [
        {"role": "user", "content": "existing question"},
        {"role": "assistant", "content": "existing answer"},
    ]
    _handle_append_command("new note", messages)

    assert len(messages) == 3
    assert messages[0]["content"] == "existing question"
    assert messages[2]["content"] == "new note"
