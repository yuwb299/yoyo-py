"""Tests for tool_bash handling of non-string commands.

LLMs sometimes send `command` as a non-string type:
- A list: {"command": ["echo", "hi"]}  (very common JSON mistake)
- A number: {"command": 42}
- None: {"command": null}

Previous behavior:
- list  → passed to subprocess.run with shell=True, which silently uses only
          list[0] as the command and ignores the rest → empty output, no error.
          The LLM gets no signal its args were malformed.
- int   → subprocess.run(42, shell=True) → cryptic "'int' object is not iterable".
- None  → handled by the empty check (acceptable).

All should return a clear param-named [ERROR] so the LLM can self-correct.
"""

import pytest

from src.tools import tool_bash


def test_list_command_returns_clear_error():
    """A list command (common JSON mistake) must not silently run as a partial shell command."""
    result = tool_bash(["echo", "hi"])
    assert "[ERROR]" in result
    assert "command" in result.lower()
    # Must NOT look like it ran successfully
    assert "hi" not in result.split("[ERROR]")[0]


def test_int_command_returns_clear_error():
    """An int command must not leak a cryptic subprocess TypeError."""
    result = tool_bash(42)
    assert "[ERROR]" in result
    assert "command" in result.lower()
    # The cryptic internal message must not leak
    assert "not iterable" not in result


def test_none_command_handled_cleanly():
    """None command should produce a clear error (not a crash)."""
    result = tool_bash(None)
    assert "[ERROR]" in result or "empty" in result.lower()


def test_dict_command_returns_clear_error():
    """A dict command must be rejected with a clear message."""
    result = tool_bash({"cmd": "echo hi"})
    assert "[ERROR]" in result
    assert "command" in result.lower()


def test_string_command_still_works():
    """Regression: a normal string command still runs."""
    result = tool_bash("echo regression_ok")
    assert "regression_ok" in result
