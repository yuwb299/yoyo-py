"""Tests for Agent._validate_messages — conversation consistency checker."""

import pytest
from src.agent import Agent


class TestValidateMessages:
    """Validate that _validate_messages catches common conversation malformations."""

    def test_valid_simple_conversation(self):
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        issues = Agent._validate_messages(messages)
        assert issues == []

    def test_valid_tool_conversation(self):
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "List files"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "tc_1", "type": "function", "function": {"name": "bash", "arguments": '{"command": "ls"}'}}
            ]},
            {"role": "tool", "tool_call_id": "tc_1", "content": "file1.py\nfile2.py"},
            {"role": "assistant", "content": "Here are the files: file1.py, file2.py"},
        ]
        issues = Agent._validate_messages(messages)
        assert issues == []

    def test_consecutive_user_messages(self):
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
            {"role": "user", "content": "Are you there?"},
        ]
        issues = Agent._validate_messages(messages)
        assert len(issues) >= 1
        assert any("consecutive user" in i.lower() for i in issues)

    def test_consecutive_assistant_messages(self):
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
            {"role": "assistant", "content": "How can I help?"},
        ]
        issues = Agent._validate_messages(messages)
        assert len(issues) >= 1
        assert any("consecutive assistant" in i.lower() for i in issues)

    def test_tool_without_tool_calls(self):
        """Tool message without a preceding assistant tool_call."""
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Do something"},
            {"role": "tool", "tool_call_id": "tc_1", "content": "output"},
        ]
        issues = Agent._validate_messages(messages)
        assert len(issues) >= 1
        assert any("tool" in i.lower() and "tool_calls" in i.lower() for i in issues)

    def test_missing_tool_response(self):
        """Assistant has tool_calls but no matching tool response."""
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "List files"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "tc_1", "type": "function", "function": {"name": "bash", "arguments": '{"command": "ls"}'}}
            ]},
            {"role": "assistant", "content": "Here are the files."},
        ]
        issues = Agent._validate_messages(messages)
        assert len(issues) >= 1
        assert any("missing" in i.lower() or "unanswered" in i.lower() for i in issues)

    def test_starts_with_user(self):
        """Valid conversation starting with user (no system prompt)."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]
        issues = Agent._validate_messages(messages)
        assert issues == []

    def test_tool_call_id_mismatch(self):
        """Tool response references a different tool_call_id."""
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "List files"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "tc_1", "type": "function", "function": {"name": "bash", "arguments": '{"command": "ls"}'}}
            ]},
            {"role": "tool", "tool_call_id": "tc_WRONG", "content": "output"},
        ]
        issues = Agent._validate_messages(messages)
        assert len(issues) >= 1
        assert any("mismatch" in i.lower() or "unmatched" in i.lower() for i in issues)

    def test_empty_conversation(self):
        issues = Agent._validate_messages([])
        assert issues == []

    def test_system_only(self):
        issues = Agent._validate_messages([{"role": "system", "content": "prompt"}])
        assert issues == []
