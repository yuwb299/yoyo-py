"""Tests for tool_bash handling of empty/whitespace commands.

The LLM occasionally sends an empty or whitespace-only command string
(usually a malformed tool call). The previous behavior returned an empty
string with no signal, leaving the LLM unable to tell whether:
- the command ran and produced no output, or
- the command was empty / invalid

An explicit message tells the LLM what went wrong so it can self-correct.
"""

from src.tools import tool_bash


def test_empty_command_returns_clear_message():
    """Empty command should not silently return ''."""
    result = tool_bash("")
    assert result, "empty command must return a non-empty message"
    assert "empty" in result.lower(), f"should explain the command was empty, got: {result!r}"


def test_whitespace_command_returns_clear_message():
    """Whitespace-only command should be treated as empty."""
    result = tool_bash("   ")
    assert result, "whitespace command must return a non-empty message"
    assert "empty" in result.lower(), f"should explain the command was empty, got: {result!r}"


def test_normal_command_still_works():
    """Regression: a real command still runs and returns output."""
    result = tool_bash("echo hello")
    assert "hello" in result, f"normal command should still work, got: {result!r}"


def test_command_with_only_newlines_treated_as_empty():
    """A command that's just whitespace/newlines is effectively empty."""
    result = tool_bash("\n\t  \n")
    assert result, "got: {result!r}"
    assert "empty" in result.lower()
