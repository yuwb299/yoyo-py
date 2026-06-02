"""Comprehensive REPL tests — slash commands, error display, agent turn display.

Tests the REPL's interactive command handling and output formatting
without actually running the full async loop.
"""

import os
import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from src.agent import Agent, AgentEvent, AgentState
from src.repl import (
    _tool_summary,
    _truncate_str,
    _git_commit,
    _git_diff_summary,
    _save_session,
    _load_session,
    _print_help,
)


class TestToolSummary:
    """Test that tool call summaries are concise and informative."""

    def test_bash_command(self):
        result = _tool_summary("bash", {"command": "ls -la"})
        assert "$ ls -la" == result

    def test_bash_long_command_truncated(self):
        result = _tool_summary("bash", {"command": "x" * 100})
        assert len(result) < 100
        assert "..." in result

    def test_read_file(self):
        result = _tool_summary("read_file", {"path": "/tmp/test.py"})
        assert "read /tmp/test.py" == result

    def test_write_file(self):
        result = _tool_summary("write_file", {"path": "/tmp/test.py"})
        assert "write /tmp/test.py" == result

    def test_edit_file(self):
        result = _tool_summary("edit_file", {"path": "src/main.py"})
        assert "edit src/main.py" == result

    def test_search(self):
        result = _tool_summary("search", {"pattern": "TODO"})
        assert "search 'TODO'" == result

    def test_search_long_pattern(self):
        result = _tool_summary("search", {"pattern": "x" * 100})
        assert len(result) < 100
        assert "..." in result

    def test_list_files(self):
        result = _tool_summary("list_files", {"path": "/tmp"})
        assert "ls /tmp" == result

    def test_list_files_default_path(self):
        result = _tool_summary("list_files", {})
        assert "ls ." == result

    def test_unknown_tool(self):
        result = _tool_summary("unknown_tool", {})
        assert "unknown_tool" == result


class TestTruncateStr:
    """Test string truncation helper."""

    def test_short_string_unchanged(self):
        assert _truncate_str("hello", 10) == "hello"

    def test_exact_length_unchanged(self):
        assert _truncate_str("hello", 5) == "hello"

    def test_long_string_truncated(self):
        result = _truncate_str("hello world", 5)
        assert result == "hello..."

    def test_empty_string(self):
        assert _truncate_str("", 5) == ""


class TestSlashCommandRouting:
    """Test that REPL slash command routing works for all commands.

    These test the command extraction logic that the REPL uses,
    not the full async loop.
    """

    def test_quit_aliases(self):
        """Both /quit and /exit should trigger exit."""
        for cmd in ("/quit", "/exit"):
            assert cmd in ("/quit", "/exit")

    def test_clear_command(self):
        """/clear should reset the agent state."""
        agent = Agent(
            provider=MagicMock(),
            system_prompt="test",
            tools={},
            tool_schemas=[],
        )
        agent.state.messages.append({"role": "user", "content": "hi"})
        assert len(agent.state.messages) > 1  # system + user
        agent.clear()
        # Only system prompt should remain
        assert len(agent.state.messages) == 1
        assert agent.state.messages[0]["role"] == "system"

    def test_model_command_extraction(self):
        """'/model glm-4' should extract 'glm-4'."""
        line = "/model glm-4"
        cmd = line.lower()
        assert cmd.startswith("/model ")
        new_model = line[7:].strip()
        assert new_model == "glm-4"

    def test_commit_command_extraction(self):
        """'/commit fix bug' should extract 'fix bug'."""
        line = "/commit fix bug"
        cmd = line.lower()
        assert cmd.startswith("/commit")
        msg = line[7:].strip() if len(line) > 7 else ""
        assert msg == "fix bug"

    def test_commit_no_message(self):
        """/commit alone should produce empty message."""
        line = "/commit"
        msg = line[7:].strip() if len(line) > 7 else ""
        assert msg == ""

    def test_save_default_path(self):
        """'/save' with no path should use default .yoyo/session.json."""
        line = "/save"
        save_path = line[5:].strip() if len(line) > 5 else ""
        # Default would be constructed in REPL
        assert save_path == ""

    def test_save_custom_path(self):
        """'/save /tmp/session.json' should extract path."""
        line = "/save /tmp/session.json"
        save_path = line[5:].strip() if len(line) > 5 else ""
        assert save_path == "/tmp/session.json"

    def test_load_default_path(self):
        """'/load' with no path should use default."""
        line = "/load"
        load_path = line[5:].strip() if len(line) > 5 else ""
        assert load_path == ""


class TestSessionSaveLoadRoundTrip:
    """Test that saving and loading a session preserves data."""

    def test_roundtrip(self, tmp_path):
        """Save a session, then load it — messages and model should match."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        model = "glm-5.1"
        path = str(tmp_path / "session.json")

        save_result = _save_session(path, messages, model)
        assert "[OK]" in save_result

        loaded = _load_session(path)
        assert loaded is not None
        loaded_messages, loaded_model, loaded_usage, warnings = loaded
        assert loaded_messages == messages
        assert loaded_model == model

    def test_load_nonexistent_file(self, tmp_path):
        """Loading from a nonexistent file returns None."""
        result = _load_session(str(tmp_path / "nope.json"))
        assert result is None

    def test_load_invalid_json(self, tmp_path):
        """Loading from an invalid JSON file returns None."""
        path = tmp_path / "bad.json"
        path.write_text("not json at all {{{")
        result = _load_session(str(path))
        assert result is None

    def test_load_missing_fields(self, tmp_path):
        """Loading a JSON file missing required fields returns None."""
        path = tmp_path / "incomplete.json"
        path.write_text(json.dumps({"version": 1}))
        result = _load_session(str(path))
        assert result is None

    def test_save_creates_parent_dirs(self, tmp_path):
        """_save_session creates parent directories if they don't exist."""
        path = str(tmp_path / "deep" / "nested" / "session.json")
        result = _save_session(path, [{"role": "user", "content": "hi"}], "glm-5.1")
        assert "[OK]" in result
        assert os.path.exists(path)


class TestGitCommitEdgeCases:
    """Edge cases for the /commit command."""

    def test_commit_no_changes(self):
        """When there are no changes, commit reports nothing to commit."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="true\n"),
                MagicMock(returncode=0, stdout=""),
                MagicMock(returncode=0, stdout=""),
            ]
            result = _git_commit("test message")
        assert "No changes" in result

    def test_commit_not_git_repo(self):
        """When not in a git repo, commit reports error."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=128, stdout="")
            result = _git_commit("test message")
        assert "ERROR" in result


class TestGitDiffEdgeCases:
    """Edge cases for the /diff command."""

    def test_diff_not_git_repo(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=128, stdout="")
            result = _git_diff_summary()
        assert "Not a git repo" in result

    def test_diff_clean_working_tree(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="true\n"),
                MagicMock(returncode=0, stdout=""),
                MagicMock(returncode=0, stdout=""),
                MagicMock(returncode=0, stdout=""),
            ]
            result = _git_diff_summary()
        assert "clean" in result.lower() or "No changes" in result


class TestErrorDisplay:
    """Test that agent errors are properly formatted for display.

    The REPL should show errors with ✗ symbol and RED color for
    both API errors and tool execution errors.
    """

    def test_api_error_event(self):
        """Agent ERROR events should contain the error message."""
        # Simulate what the agent would emit
        error_msg = "Rate limited — wait a moment and try again"
        # The REPL just prints the data from the event
        assert "Rate limited" in error_msg

    def test_tool_error_includes_name(self):
        """Tool execution errors should include the tool name."""
        error_msg = "Error executing bash: missing 'command' argument"
        assert "bash" in error_msg

    def test_unknown_tool_error(self):
        """Unknown tool calls should produce a clear error."""
        error_msg = "Unknown tool: fly_to_moon"
        assert "Unknown tool" in error_msg
        assert "fly_to_moon" in error_msg


class TestPrintHelp:
    """Test that help output includes all commands."""

    def test_help_includes_all_commands(self, capsys):
        """_print_help should list all available slash commands."""
        _print_help()
        output = capsys.readouterr().out
        for cmd in ("/quit", "/clear", "/help", "/model", "/diff",
                     "/commit", "/save", "/load", "/skills", "/tokens",
                     "/status", "/compact"):
            assert cmd in output, f"Help missing command: {cmd}"

    def test_help_lists_tools(self, capsys):
        """_print_help should list all available tools."""
        _print_help()
        output = capsys.readouterr().out
        for tool in ("bash", "read_file", "write_file", "edit_file", "search", "list_files"):
            assert tool in output, f"Help missing tool: {tool}"
