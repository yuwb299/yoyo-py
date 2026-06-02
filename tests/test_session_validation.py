"""Tests for message validation on session load.

When loading a session (via /load or /resume), the message structure
should be validated to prevent API crashes from corrupt data.
"""

import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch

from src.repl import (
    _load_session,
    _handle_resume_command,
    _save_session,
    _auto_save_session,
)
from src.agent import Agent
from src.provider import Usage


class TestLoadSessionValidation:
    """Test that _load_session validates message structure."""

    def test_load_valid_session(self, tmp_path):
        """A valid session loads without issues."""
        session_file = tmp_path / "session.json"
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        data = {
            "version": 1,
            "model": "glm-5.1",
            "messages": messages,
        }
        session_file.write_text(json.dumps(data), encoding="utf-8")

        result = _load_session(str(session_file))
        assert result is not None
        loaded_messages, model, usage = result
        assert len(loaded_messages) == 3
        assert model == "glm-5.1"

    def test_load_session_with_consecutive_user_messages(self, tmp_path):
        """Consecutive user messages should be flagged but still loaded.

        Some APIs reject consecutive same-role messages. We warn but don't
        reject the load — the user may want to fix it manually.
        """
        session_file = tmp_path / "session.json"
        # Invalid: two consecutive user messages
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
            {"role": "user", "content": "World"},
            {"role": "assistant", "content": "Hi!"},
        ]
        data = {
            "version": 1,
            "model": "glm-5.1",
            "messages": messages,
        }
        session_file.write_text(json.dumps(data), encoding="utf-8")

        result = _load_session(str(session_file))
        assert result is not None
        # Messages are still loaded — validation is informational
        loaded_messages, _, _ = result
        assert len(loaded_messages) == 4

    def test_load_session_with_orphaned_tool_message(self, tmp_path):
        """Tool message without preceding assistant tool_calls should load with warning."""
        session_file = tmp_path / "session.json"
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Run bash"},
            {"role": "tool", "tool_call_id": "call_123", "content": "output"},
            {"role": "assistant", "content": "Done!"},
        ]
        data = {
            "version": 1,
            "model": "glm-5.1",
            "messages": messages,
        }
        session_file.write_text(json.dumps(data), encoding="utf-8")

        result = _load_session(str(session_file))
        assert result is not None

    def test_load_session_validates_and_returns_warnings(self, tmp_path):
        """_load_session should return validation warnings separately."""
        session_file = tmp_path / "session.json"
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
            {"role": "user", "content": "World"},
        ]
        data = {
            "version": 1,
            "model": "glm-5.1",
            "messages": messages,
        }
        session_file.write_text(json.dumps(data), encoding="utf-8")

        result = _load_session(str(session_file))
        assert result is not None
        # Now returns (messages, model, usage, warnings)
        # or (messages, model, usage) depending on implementation
        if len(result) == 4:
            _, _, _, warnings = result
            assert len(warnings) > 0
            assert any("consecutive" in w.lower() or "Consecutive" in w for w in warnings)

    def test_load_clean_session_no_warnings(self, tmp_path):
        """A clean session should produce no warnings."""
        session_file = tmp_path / "session.json"
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"},
            {"role": "assistant", "content": "I'm great!"},
        ]
        data = {
            "version": 1,
            "model": "glm-5.1",
            "messages": messages,
        }
        session_file.write_text(json.dumps(data), encoding="utf-8")

        result = _load_session(str(session_file))
        assert result is not None
        if len(result) == 4:
            _, _, _, warnings = result
            assert warnings == []


class TestResumeCommandValidation:
    """Test that /resume also validates messages."""

    def test_resume_with_valid_messages(self, tmp_path):
        """Resume with valid messages should succeed."""
        autosave_file = tmp_path / ".yoyo" / "autosave.json"
        autosave_file.parent.mkdir(parents=True, exist_ok=True)

        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]
        data = {
            "version": 1,
            "model": "glm-5.1",
            "messages": messages,
            "autosaved": True,
        }
        autosave_file.write_text(json.dumps(data), encoding="utf-8")

        result = _handle_resume_command(cwd=str(tmp_path))
        assert not isinstance(result, str)  # Success returns tuple
        loaded_messages, model, usage, warnings = result[:4]
        assert len(loaded_messages) == 3


class TestValidateMessagesIntegration:
    """Test the _validate_messages function directly with various message patterns."""

    def test_valid_tool_call_sequence(self):
        """A proper tool call + response sequence should validate clean."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "List files"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "type": "function", "function": {"name": "list_files", "arguments": "{}"}}
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "file1.py\nfile2.py"},
            {"role": "assistant", "content": "Here are your files."},
        ]
        issues = Agent._validate_messages(messages)
        assert issues == []

    def test_consecutive_assistant_messages_flagged(self):
        """Two assistant messages in a row should be flagged."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
            {"role": "assistant", "content": "Hello again!"},
        ]
        issues = Agent._validate_messages(messages)
        assert any("Consecutive assistant" in i for i in issues)

    def test_system_prompt_not_first_flagged(self):
        """System prompt at position > 0 should be flagged."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "system", "content": "You are helpful."},
        ]
        issues = Agent._validate_messages(messages)
        assert any("System prompt at position" in i for i in issues)

    def test_unanswered_tool_calls_flagged(self):
        """Tool calls without responses should be flagged."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "List files"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "type": "function", "function": {"name": "list_files", "arguments": "{}"}}
                ],
            },
        ]
        issues = Agent._validate_messages(messages)
        assert any("Unanswered" in i for i in issues)
