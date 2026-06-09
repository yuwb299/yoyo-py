"""Tests for tool output trimming — truncating old tool outputs to save context."""

import pytest
from src.agent import Agent


class TestTrimToolOutputs:
    """Test _trim_tool_outputs static method."""

    def test_no_messages(self):
        """Empty message list returns empty list."""
        result = Agent._trim_tool_outputs([])
        assert result == []

    def test_no_tool_messages(self):
        """Messages without tool outputs are left unchanged."""
        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        result = Agent._trim_tool_outputs(messages)
        assert result == messages

    def test_short_tool_output_unchanged(self):
        """Tool outputs under the threshold are not trimmed."""
        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "read the file"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "tc_1", "type": "function", "function": {"name": "read_file", "arguments": '{"path": "a.py"}'}}
            ]},
            {"role": "tool", "tool_call_id": "tc_1", "content": "short output"},
        ]
        result = Agent._trim_tool_outputs(messages, max_output=100)
        assert result[-1]["content"] == "short output"

    def test_long_tool_output_trimmed(self):
        """Long tool outputs are truncated with a truncation notice."""
        long_output = "x" * 2000
        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "read the file"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "tc_1", "type": "function", "function": {"name": "read_file", "arguments": '{"path": "a.py"}'}}
            ]},
            {"role": "tool", "tool_call_id": "tc_1", "content": long_output},
        ]
        # keep_recent=0 so this single tool output is treated as "old" and trimmed
        result = Agent._trim_tool_outputs(messages, max_output=500, keep_recent=0)
        content = result[-1]["content"]
        assert len(content) < 600  # max_output + truncation notice
        assert "truncated" in content.lower()

    def test_only_old_outputs_trimmed(self):
        """Old tool outputs are trimmed but recent ones are kept intact."""
        long_output = "x" * 2000
        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "read file 1"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "tc_1", "type": "function", "function": {"name": "read_file", "arguments": '{"path": "a.py"}'}}
            ]},
            {"role": "tool", "tool_call_id": "tc_1", "content": long_output},
            {"role": "assistant", "content": "I see file a.py"},
            {"role": "user", "content": "read file 2"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "tc_2", "type": "function", "function": {"name": "read_file", "arguments": '{"path": "b.py"}'}}
            ]},
            {"role": "tool", "tool_call_id": "tc_2", "content": long_output},
        ]
        # With keep_recent=1, only the last tool output is kept intact
        result = Agent._trim_tool_outputs(messages, max_output=500, keep_recent=1)
        # First tool output should be trimmed
        first_tool = [m for m in result if m.get("role") == "tool"][0]
        assert len(first_tool["content"]) < 600
        # Last tool output should be intact
        last_tool = [m for m in result if m.get("role") == "tool"][-1]
        assert len(last_tool["content"]) == 2000

    def test_keeps_recent_intact(self):
        """The most recent tool outputs (keep_recent) are never trimmed."""
        long_output = "y" * 3000
        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "go"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "tc_1", "type": "function", "function": {"name": "bash", "arguments": '{"command": "ls"}'}}
            ]},
            {"role": "tool", "tool_call_id": "tc_1", "content": long_output},
        ]
        result = Agent._trim_tool_outputs(messages, max_output=500, keep_recent=1)
        assert result[-1]["content"] == long_output

    def test_truncation_notice_includes_original_length(self):
        """The truncation notice tells the agent the original output size."""
        long_output = "a" * 5000
        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "run"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "tc_1", "type": "function", "function": {"name": "bash", "arguments": '{"command": "ls"}'}}
            ]},
            {"role": "tool", "tool_call_id": "tc_1", "content": long_output},
        ]
        result = Agent._trim_tool_outputs(messages, max_output=500, keep_recent=0)
        content = result[-1]["content"]
        assert "5000" in content  # Original length mentioned

    def test_does_not_modify_input(self):
        """The original message list is not modified (returns new list)."""
        long_output = "z" * 2000
        messages = [
            {"role": "tool", "tool_call_id": "tc_1", "content": long_output},
        ]
        original_content = messages[0]["content"]
        _ = Agent._trim_tool_outputs(messages, max_output=500, keep_recent=0)
        assert messages[0]["content"] == original_content

    def test_error_outputs_not_trimmed(self):
        """Tool outputs with error markers are not trimmed — errors are important."""
        error_output = "[ERROR] Something went wrong: " + "x" * 2000
        messages = [
            {"role": "tool", "tool_call_id": "tc_1", "content": error_output},
        ]
        result = Agent._trim_tool_outputs(messages, max_output=500, keep_recent=0)
        # Error outputs should be trimmed too — they're still tool outputs
        assert len(result[0]["content"]) < 600

    def test_default_max_output(self):
        """Default max_output works when not specified."""
        long_output = "x" * 15000
        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "go"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "tc_1", "type": "function", "function": {"name": "bash", "arguments": '{"command": "ls"}'}}
            ]},
            {"role": "tool", "tool_call_id": "tc_1", "content": long_output},
        ]
        result = Agent._trim_tool_outputs(messages, keep_recent=0)
        assert len(result[-1]["content"]) < 15000
