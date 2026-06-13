"""Tests for /history --last N and --exchange flags."""

import pytest
from src.repl import _format_history


class TestHistoryLastFlag:
    """Test /history --last N flag to show only the last N messages."""

    def _make_messages(self, n: int) -> list[dict]:
        """Create n user/assistant message pairs."""
        msgs = [{"role": "system", "content": "sys"}]
        for i in range(n):
            msgs.append({"role": "user", "content": f"msg {i}"})
            msgs.append({"role": "assistant", "content": f"reply {i}"})
        return msgs

    def test_last_flag_shows_only_last_n_messages(self):
        """--last N should only show the last N messages."""
        msgs = self._make_messages(10)  # 21 messages total
        result = _format_history(msgs, last=4)
        # Should show 4 messages, not all 21
        # The output should contain "msg 9" but not "msg 0"
        assert "msg 9" in result
        assert "msg 0" not in result

    def test_last_larger_than_history_shows_all(self):
        """--last N where N > total messages should show all messages."""
        msgs = self._make_messages(3)  # 7 messages
        result = _format_history(msgs, last=100)
        assert "msg 0" in result
        assert "msg 2" in result

    def test_last_zero_shows_nothing(self):
        """--last 0 should show no messages (just header)."""
        msgs = self._make_messages(3)
        result = _format_history(msgs, last=0)
        assert "msg 0" not in result
        assert "msg 1" not in result

    def test_last_preserves_system_message(self):
        """System message should always be shown regardless of --last."""
        msgs = self._make_messages(10)
        result = _format_history(msgs, last=4)
        assert "system prompt" in result

    def test_last_default_shows_all(self):
        """Without --last, all messages should be shown."""
        msgs = self._make_messages(3)
        result = _format_history(msgs)
        assert "msg 0" in result
        assert "msg 2" in result

    def test_last_includes_tool_messages(self):
        """--last should include tool messages in the count."""
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "old question"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "t1", "type": "function", "function": {"name": "bash", "arguments": '{"command": "ls"}'}}
            ]},
            {"role": "tool", "tool_call_id": "t1", "content": "output"},
            {"role": "assistant", "content": "old answer"},
            {"role": "user", "content": "new question"},
            {"role": "assistant", "content": "new answer"},
        ]
        result = _format_history(msgs, last=2)
        assert "new question" in result
        assert "old answer" not in result


class TestHistoryExchangeFlag:
    """Test /history --exchange flag to hide tool messages."""

    def test_exchange_hides_tool_messages(self):
        """--exchange should hide tool role messages."""
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "t1", "type": "function", "function": {"name": "bash", "arguments": '{"command": "ls"}'}}
            ]},
            {"role": "tool", "tool_call_id": "t1", "content": "file1.txt"},
            {"role": "assistant", "content": "I found files."},
        ]
        result = _format_history(msgs, exchange=True)
        assert "tool" not in result.lower() or "tool [" not in result

    def test_exchange_keeps_assistant_tool_calls(self):
        """--exchange should keep assistant messages with tool_calls."""
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "t1", "type": "function", "function": {"name": "bash", "arguments": '{"command": "ls"}'}}
            ]},
            {"role": "tool", "tool_call_id": "t1", "content": "output"},
            {"role": "assistant", "content": "done"},
        ]
        result = _format_history(msgs, exchange=True)
        assert "bash" in result

    def test_exchange_shows_normal_messages(self):
        """--exchange should show system, user, and assistant messages normally."""
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        result = _format_history(msgs, exchange=True)
        assert "hello" in result
        assert "hi there" in result

    def test_exchange_and_last_combined(self):
        """--exchange and --last should work together."""
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "t1", "type": "function", "function": {"name": "bash", "arguments": '{}'}}
            ]},
            {"role": "tool", "tool_call_id": "t1", "content": "output"},
            {"role": "user", "content": "new question"},
            {"role": "assistant", "content": "new answer"},
        ]
        result = _format_history(msgs, last=3, exchange=True)
        assert "new question" in result
        assert "new answer" in result
        # Tool message should be hidden
        assert "tool [" not in result
