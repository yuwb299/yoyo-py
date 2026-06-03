"""Tests for /revert command — undo last conversation exchange(s)."""

import pytest
from src.repl import _handle_revert_command


class TestRevertCommand:
    """Test that /revert removes the last user+assistant exchange from history."""

    def _make_messages(self, *pairs: list[tuple[str, str]]) -> list[dict]:
        """Build a message list from (role, content) pairs, starting with system."""
        msgs = [{"role": "system", "content": "You are a helper."}]
        for role, content in pairs:
            msgs.append({"role": role, "content": content})
        return msgs

    def test_revert_no_messages(self):
        """Reverting with only system prompt returns an error."""
        messages = self._make_messages()
        result = _handle_revert_command(messages)
        assert isinstance(result, str)
        assert "nothing" in result.lower() or "no" in result.lower()

    def test_revert_single_exchange(self):
        """Reverting removes one user+assistant pair."""
        messages = self._make_messages(
            ("user", "hello"),
            ("assistant", "hi there"),
        )
        result = _handle_revert_command(messages)
        assert isinstance(result, tuple)
        new_messages, removed_count = result
        # Should have removed 2 messages (user + assistant)
        assert removed_count == 2
        # Only system message should remain
        assert len(new_messages) == 1
        assert new_messages[0]["role"] == "system"

    def test_revert_two_exchanges(self):
        """Reverting with count=2 removes two user+assistant pairs."""
        messages = self._make_messages(
            ("user", "first question"),
            ("assistant", "first answer"),
            ("user", "second question"),
            ("assistant", "second answer"),
        )
        result = _handle_revert_command(messages, count=2)
        assert isinstance(result, tuple)
        new_messages, removed_count = result
        assert removed_count == 4
        assert len(new_messages) == 1
        assert new_messages[0]["role"] == "system"

    def test_revert_with_tool_calls(self):
        """Reverting removes assistant with tool_calls and subsequent tool responses."""
        messages = self._make_messages(
            ("user", "list files"),
        )
        messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "tc1", "function": {"name": "bash", "arguments": '{"command": "ls"}'}}],
        })
        messages.append({"role": "tool", "tool_call_id": "tc1", "content": "file1.py\nfile2.py"})
        messages.append({"role": "assistant", "content": "Here are the files."})

        result = _handle_revert_command(messages)
        assert isinstance(result, tuple)
        new_messages, removed_count = result
        # Removed: user + assistant(tool_calls) + tool + assistant(final)
        assert removed_count == 4
        assert len(new_messages) == 1

    def test_revert_partial_exchange_only_user(self):
        """Reverting when the last message is user-only still removes it."""
        messages = self._make_messages(
            ("user", "hello"),
            ("assistant", "hi"),
            ("user", "next question"),
        )
        result = _handle_revert_command(messages)
        assert isinstance(result, tuple)
        new_messages, removed_count = result
        # Removed: user (the last incomplete exchange)
        assert removed_count == 1
        # Should have system + user(hello) + assistant(hi) left
        assert len(new_messages) == 3

    def test_revert_preserves_system(self):
        """System prompt is never removed by revert."""
        messages = self._make_messages(
            ("user", "hello"),
            ("assistant", "hi"),
        )
        assert len(messages) == 3
        result = _handle_revert_command(messages)
        assert isinstance(result, tuple)
        new_messages, _ = result
        assert new_messages[0]["role"] == "system"

    def test_revert_count_exceeds_messages(self):
        """Reverting more exchanges than exist just removes all non-system messages."""
        messages = self._make_messages(
            ("user", "hello"),
            ("assistant", "hi"),
        )
        result = _handle_revert_command(messages, count=10)
        assert isinstance(result, tuple)
        new_messages, removed_count = result
        assert len(new_messages) == 1
        assert removed_count == 2

    def test_revert_count_zero(self):
        """Revert with count=0 does nothing."""
        messages = self._make_messages(
            ("user", "hello"),
            ("assistant", "hi"),
        )
        result = _handle_revert_command(messages, count=0)
        assert isinstance(result, str)
        # Should indicate nothing was done
        assert "0" in result or "nothing" in result.lower() or "no" in result.lower()
