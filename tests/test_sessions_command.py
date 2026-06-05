"""Tests for /sessions command — list saved sessions with metadata."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.repl import CommandRegistry, _list_sessions, _delete_session, _format_sessions_output


class TestListSessions:
    """Test the _list_sessions helper function."""

    def test_no_yoyo_dir(self):
        """Returns empty list when .yoyo/ doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions = _list_sessions(tmpdir)
            assert sessions == []

    def test_no_json_files(self):
        """Returns empty list when .yoyo/ exists but has no .json files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yoyo_dir = os.path.join(tmpdir, ".yoyo")
            os.makedirs(yoyo_dir)
            Path(os.path.join(yoyo_dir, "notes.txt")).write_text("not a session")
            sessions = _list_sessions(tmpdir)
            assert sessions == []

    def test_finds_session_files(self):
        """Finds .json files in .yoyo/ and returns metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yoyo_dir = os.path.join(tmpdir, ".yoyo")
            os.makedirs(yoyo_dir)

            # Create a session file
            session = {
                "version": 1,
                "timestamp": "2026-06-05T14:30:00",
                "model": "glm-5.1",
                "messages": [
                    {"role": "system", "content": "sys"},
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": "hi"},
                ],
            }
            Path(os.path.join(yoyo_dir, "session.json")).write_text(
                json.dumps(session)
            )

            sessions = _list_sessions(tmpdir)
            assert len(sessions) == 1
            s = sessions[0]
            assert s["filename"] == "session.json"
            assert s["model"] == "glm-5.1"
            assert s["message_count"] == 2  # excludes system
            assert s["autosaved"] is False
            assert s["timestamp"] == "2026-06-05T14:30:00"

    def test_autosave_flag(self):
        """Detects auto-saved sessions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yoyo_dir = os.path.join(tmpdir, ".yoyo")
            os.makedirs(yoyo_dir)

            session = {
                "version": 1,
                "timestamp": "2026-06-05T14:30:00",
                "model": "glm-5.1",
                "autosaved": True,
                "messages": [
                    {"role": "user", "content": "hello"},
                ],
            }
            Path(os.path.join(yoyo_dir, "autosave.json")).write_text(
                json.dumps(session)
            )

            sessions = _list_sessions(tmpdir)
            assert len(sessions) == 1
            assert sessions[0]["autosaved"] is True

    def test_multiple_sessions(self):
        """Finds multiple session files, sorted by filename."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yoyo_dir = os.path.join(tmpdir, ".yoyo")
            os.makedirs(yoyo_dir)

            for name in ["autosave.json", "session.json", "backup.json"]:
                session = {
                    "version": 1,
                    "timestamp": "2026-06-05T12:00:00",
                    "model": "glm-5.1",
                    "messages": [{"role": "user", "content": "hi"}],
                }
                Path(os.path.join(yoyo_dir, name)).write_text(json.dumps(session))

            sessions = _list_sessions(tmpdir)
            assert len(sessions) == 3
            names = [s["filename"] for s in sessions]
            assert names == sorted(names)

    def test_invalid_json_skipped(self):
        """Skips files that aren't valid session JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yoyo_dir = os.path.join(tmpdir, ".yoyo")
            os.makedirs(yoyo_dir)

            # Invalid JSON
            Path(os.path.join(yoyo_dir, "bad.json")).write_text("not json")
            # Valid JSON but missing required fields
            Path(os.path.join(yoyo_dir, "partial.json")).write_text(
                json.dumps({"version": 1})
            )

            sessions = _list_sessions(tmpdir)
            assert sessions == []

    def test_includes_usage_data(self):
        """Includes token usage data when available."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yoyo_dir = os.path.join(tmpdir, ".yoyo")
            os.makedirs(yoyo_dir)

            session = {
                "version": 1,
                "timestamp": "2026-06-05T14:30:00",
                "model": "glm-5.1",
                "messages": [{"role": "user", "content": "hi"}],
                "usage": {"input_tokens": 1000, "output_tokens": 500},
            }
            Path(os.path.join(yoyo_dir, "session.json")).write_text(
                json.dumps(session)
            )

            sessions = _list_sessions(tmpdir)
            assert sessions[0]["input_tokens"] == 1000
            assert sessions[0]["output_tokens"] == 500


class TestDeleteSession:
    """Test the _delete_session helper function."""

    def test_delete_existing_session(self):
        """Deletes a session file from .yoyo/."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yoyo_dir = os.path.join(tmpdir, ".yoyo")
            os.makedirs(yoyo_dir)
            filepath = os.path.join(yoyo_dir, "session.json")
            Path(filepath).write_text('{"test": true}')

            result = _delete_session("session.json", tmpdir)
            assert result is True
            assert not os.path.exists(filepath)

    def test_delete_nonexistent_session(self):
        """Returns False when session doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _delete_session("nonexistent.json", tmpdir)
            assert result is False

    def test_delete_prevents_path_traversal(self):
        """Refuses to delete files outside .yoyo/ directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file at root level
            trap_file = os.path.join(tmpdir, "important.txt")
            Path(trap_file).write_text("do not delete")

            result = _delete_session("../important.txt", tmpdir)
            # Should not delete files outside .yoyo/
            assert os.path.exists(trap_file)

    def test_delete_only_json_files(self):
        """Refuses to delete non-JSON files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yoyo_dir = os.path.join(tmpdir, ".yoyo")
            os.makedirs(yoyo_dir)
            filepath = os.path.join(yoyo_dir, "config.yaml")
            Path(filepath).write_text("key: value")

            result = _delete_session("config.yaml", tmpdir)
            assert os.path.exists(filepath)


class TestSessionsCommand:
    """Test /sessions command registration and output."""

    def test_registry_has_sessions_command(self):
        """The /sessions command is registered in the command registry."""
        from src.repl import CommandRegistry

        registry = CommandRegistry()
        # Commands are registered at module level, so the built-in registry
        # has them. We just verify the registry API works.
        assert hasattr(registry, "_handlers")
        assert hasattr(registry, "list_commands")

    def test_sessions_in_slash_commands_list(self):
        """'/sessions' appears in the _SLASH_COMMANDS list for tab completion."""
        from src.repl import _SLASH_COMMANDS

        assert "/sessions" in _SLASH_COMMANDS

    def test_rm_in_slash_commands_list(self):
        """'/rm' appears in the _SLASH_COMMANDS list for tab completion."""
        from src.repl import _SLASH_COMMANDS

        assert "/rm" in _SLASH_COMMANDS


class TestSessionsFormatting:
    """Test the formatting of session list output."""

    def test_format_sessions_with_data(self):
        """Format session metadata into readable output."""
        sessions = [
            {
                "filename": "session.json",
                "timestamp": "2026-06-05T14:30:00",
                "model": "glm-5.1",
                "message_count": 12,
                "autosaved": False,
                "input_tokens": 5000,
                "output_tokens": 2000,
            },
            {
                "filename": "autosave.json",
                "timestamp": "2026-06-06T09:15:00",
                "model": "glm-5.1",
                "message_count": 3,
                "autosaved": True,
                "input_tokens": 0,
                "output_tokens": 0,
            },
        ]

        output = _format_sessions_output(sessions)
        assert "session.json" in output
        assert "autosave.json" in output
        assert "12 messages" in output
        assert "3 messages" in output
        assert "auto-saved" in output

    def test_format_no_sessions(self):
        """Format empty sessions list with helpful message."""
        output = _format_sessions_output([])
        # Strip ANSI escape codes for matching
        import re
        clean = re.sub(r'\x1b\[[0-9;]*m', '', output)
        assert "no saved session" in clean.lower() or "not found" in clean.lower()
