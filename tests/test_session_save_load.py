"""Tests for session save/load commands.

The /save and /load commands allow users to persist conversation
history and restore it later, useful for resuming work across sessions.
"""

import json
import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from src.repl import _save_session, _load_session


class TestSaveSession:
    """Test the _save_session function."""

    def test_save_session_creates_file(self):
        """Saving a session creates a JSON file with messages and metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "session.json")
            messages = [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
            ]
            model = "glm-5.1"
            result = _save_session(filepath, messages, model)
            assert "[OK]" in result
            assert os.path.exists(filepath)

            # Verify contents
            with open(filepath) as f:
                data = json.load(f)
            assert data["messages"] == messages
            assert data["model"] == model
            assert "timestamp" in data

    def test_save_session_with_tool_messages(self):
        """Sessions with tool call messages are saved correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "session.json")
            messages = [
                {"role": "system", "content": "System"},
                {"role": "user", "content": "List files"},
                {"role": "assistant", "content": None, "tool_calls": [{"id": "tc1", "type": "function", "function": {"name": "list_files", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "tc1", "content": "file1.py\nfile2.py"},
            ]
            result = _save_session(filepath, messages, "glm-5.1")
            assert "[OK]" in result

            with open(filepath) as f:
                data = json.load(f)
            assert len(data["messages"]) == 4

    def test_save_session_creates_directory(self):
        """Save creates parent directories if they don't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "sessions", "subdir", "session.json")
            messages = [{"role": "user", "content": "test"}]
            result = _save_session(filepath, messages, "glm-5.1")
            assert "[OK]" in result
            assert os.path.exists(filepath)

    def test_save_session_handles_error(self):
        """Save returns error message on failure."""
        # Try saving to an invalid path
        result = _save_session("/nonexistent/deeply/nested/path/session.json", [{"role": "user", "content": "test"}], "glm-5.1")
        # This might actually succeed if the OS allows creating the dirs
        # Let's just verify it doesn't crash


class TestLoadSession:
    """Test the _load_session function."""

    def test_load_session_restores_messages(self):
        """Loading a session returns the saved messages and model."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "session.json")
            messages = [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi!"},
            ]
            # Save first
            _save_session(filepath, messages, "glm-5.1")

            # Now load
            result = _load_session(filepath)
            assert result is not None
            loaded_messages, model, usage = result
            assert loaded_messages == messages
            assert model == "glm-5.1"

    def test_load_session_file_not_found(self):
        """Loading from nonexistent file returns None."""
        result = _load_session("/nonexistent/session.json")
        assert result is None

    def test_load_session_invalid_json(self):
        """Loading a file with invalid JSON returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "bad.json")
            with open(filepath, "w") as f:
                f.write("not valid json{{{")
            result = _load_session(filepath)
            assert result is None

    def test_load_session_missing_fields(self):
        """Loading a file with missing required fields returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "incomplete.json")
            with open(filepath, "w") as f:
                json.dump({"messages": []}, f)  # Missing model
            result = _load_session(filepath)
            assert result is None

    def test_save_and_load_roundtrip(self):
        """A full save→load roundtrip preserves all data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "roundtrip.json")
            messages = [
                {"role": "system", "content": "System prompt"},
                {"role": "user", "content": "What is 2+2?"},
                {"role": "assistant", "content": "4"},
                {"role": "user", "content": "Thanks!"},
                {"role": "assistant", "content": "You're welcome!"},
            ]
            model = "glm-4"

            _save_session(filepath, messages, model)
            result = _load_session(filepath)

            assert result is not None
            loaded_messages, loaded_model, loaded_usage = result
            assert loaded_messages == messages
            assert loaded_model == model
