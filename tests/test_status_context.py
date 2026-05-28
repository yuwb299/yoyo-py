"""Tests for /status command with context window estimation."""

import os
from unittest.mock import patch


def test_status_shows_context_tokens():
    """_format_status_output should include estimated context tokens."""
    from src.repl import _format_status_output

    messages = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]
    from src.provider import Usage
    usage = Usage(input_tokens=100, output_tokens=50)

    result = _format_status_output(
        model="glm-5.1",
        cwd="/tmp",
        messages=messages,
        usage=usage,
        skills_count=3,
    )
    assert "glm-5.1" in result
    assert "/tmp" in result
    assert "3 messages" in result
    assert "context" in result.lower()


def test_status_shows_all_fields():
    """_format_status_output should include model, cwd, messages, tokens, skills."""
    from src.repl import _format_status_output
    from src.provider import Usage

    messages = [{"role": "system", "content": "test"}]
    usage = Usage(input_tokens=500, output_tokens=200)

    result = _format_status_output(
        model="gpt-4o",
        cwd="/home/user/project",
        messages=messages,
        usage=usage,
        skills_count=7,
    )
    assert "gpt-4o" in result
    assert "/home/user/project" in result
    assert "1 message" in result
    assert "500" in result
    assert "7" in result


def test_status_empty_messages():
    """_format_status_output should handle empty messages list."""
    from src.repl import _format_status_output
    from src.provider import Usage

    result = _format_status_output(
        model="glm-5",
        cwd="/tmp",
        messages=[],
        usage=Usage(),
        skills_count=0,
    )
    assert "0 messages" in result
