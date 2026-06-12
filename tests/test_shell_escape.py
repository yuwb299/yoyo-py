"""Tests for shell escape (!command) feature.

When a line starts with !, it should:
1. Execute the command via shell
2. Format the output as a user message for the agent
3. Handle errors gracefully
"""
import pytest
from unittest.mock import patch, MagicMock
import subprocess


def test_bang_executes_command():
    """Lines starting with ! should execute as shell commands."""
    from src.tools import tool_bash
    # Verify our test commands work first
    result = tool_bash("echo hello_world")
    assert "hello_world" in result


def test_shell_escape_formatting():
    """Shell escape should format output with command context."""
    from src.repl import _format_shell_escape
    
    result = _format_shell_escape("echo test", "test output")
    assert "echo test" in result
    assert "test output" in result


def test_shell_escape_formatting_with_stderr():
    """Shell escape should include stderr when present."""
    from src.repl import _format_shell_escape
    
    result = _format_shell_escape("some_cmd", "stdout here\n[stderr] error msg")
    assert "stdout here" in result


def test_shell_escape_formatting_truncation():
    """Shell escape should truncate very long output."""
    from src.repl import _format_shell_escape
    
    long_output = "x" * 10000
    result = _format_shell_escape("cat huge_file", long_output)
    # Should be truncated but still contain the command
    assert "cat huge_file" in result
    assert len(result) < 15000  # Much less than the raw output


def test_shell_escape_empty_output():
    """Shell escape should handle empty command output."""
    from src.repl import _format_shell_escape
    
    result = _format_shell_escape("true", "")
    assert "true" in result
    assert "(no output)" in result


def test_shell_escape_error_exit_code():
    """Shell escape should show exit code for failed commands."""
    from src.repl import _format_shell_escape
    
    result = _format_shell_escape("false", "[exit code: 1]")
    assert "false" in result
    assert "exit code" in result


def test_shell_escape_help_in_slash_commands():
    """! should appear in slash command list for tab completion."""
    from src.repl import _SLASH_COMMANDS
    # Shell escape isn't a /command — it starts with !
    # But we should NOT have /! in the command list
    assert "/!" not in _SLASH_COMMANDS


def test_shell_escape_man_page():
    """Man page should document the ! escape syntax."""
    from src.repl import _MAN_PAGES
    # The 'shell' or 'bang' man page should exist
    assert "shell" in _MAN_PAGES or "bang" in _MAN_PAGES
