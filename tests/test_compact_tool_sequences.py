"""Tests for compact_messages handling of tool call sequences.

The compaction must never leave orphaned tool messages — tool messages
(role="tool") must always be preceded by an assistant message with tool_calls.
If compaction would split a tool-call sequence, it must either include the
whole sequence in "recent" or drop the orphaned tool messages.
"""

from __future__ import annotations

from src.agent import Agent


def _make_system() -> dict:
    return {"role": "system", "content": "You are a helpful assistant."}


def _make_user(text: str) -> dict:
    return {"role": "user", "content": text}


def _make_assistant(text: str = "", tool_calls: list[dict] | None = None) -> dict:
    msg: dict = {"role": "assistant", "content": text or None}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return msg


def _make_tool(tool_call_id: str, content: str) -> dict:
    return {"role": "tool", "tool_call_id": tool_call_id, "content": content}


def _make_tool_call(call_id: str, name: str, args: str = "{}") -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": args},
    }


class TestCompactToolSequences:
    """Ensure compact_messages never creates orphaned tool messages."""

    def test_orphaned_tool_message_is_dropped(self):
        """If a tool message would be the first in 'recent', it's dropped."""
        messages = [
            _make_system(),
            _make_user("hello"),
            _make_assistant("hi"),
            _make_user("read a file"),
            # Tool call sequence starts here — assistant calls a tool
            _make_assistant(tool_calls=[_make_tool_call("tc1", "read_file")]),
            _make_tool("tc1", "file contents here"),
            _make_user("another question"),
            _make_assistant("answer"),
        ]

        # With keep_recent=2, the "recent" slice would be:
        # [tool("tc1"), user("another question")]
        # — the tool message is orphaned (no preceding assistant with tool_calls)
        result = Agent._compact_messages(messages, keep_recent=2)

        # The tool message should have been dropped
        roles = [m.get("role") for m in result]
        # No tool message should appear without a preceding assistant with tool_calls
        for i, msg in enumerate(result):
            if msg.get("role") == "tool":
                assert i > 0, "Tool message should not be first in result"
                prev = result[i - 1]
                assert prev.get("role") == "assistant" and "tool_calls" in prev, (
                    f"Tool message at index {i} has no preceding assistant with tool_calls"
                )

    def test_complete_tool_sequence_preserved(self):
        """A complete tool sequence (assistant+tool) in recent is kept intact."""
        messages = [
            _make_system(),
            _make_user("hello"),
            _make_assistant("hi"),
            _make_user("read a file"),
            _make_assistant(tool_calls=[_make_tool_call("tc1", "read_file")]),
            _make_tool("tc1", "file contents"),
            _make_user("thanks"),
        ]

        # keep_recent=4 keeps the full tool sequence
        result = Agent._compact_messages(messages, keep_recent=4)
        roles = [m.get("role") for m in result]
        # Should have: system, user(summary), assistant(tool_calls), tool, user
        assert "tool" in roles
        tool_idx = roles.index("tool")
        assert result[tool_idx - 1].get("role") == "assistant"
        assert "tool_calls" in result[tool_idx - 1]

    def test_multiple_orphaned_tools_all_dropped(self):
        """Multiple orphaned tool messages at the start of 'recent' are all dropped."""
        messages = [
            _make_system(),
            _make_user("do stuff"),
            _make_assistant(tool_calls=[
                _make_tool_call("tc1", "read_file"),
                _make_tool_call("tc2", "bash"),
            ]),
            _make_tool("tc1", "output 1"),
            _make_tool("tc2", "output 2"),
            _make_user("more stuff"),
            _make_assistant("done"),
        ]

        # keep_recent=3 would give: [tool("tc1"), tool("tc2"), user("more stuff")]
        # Both tool messages are orphaned
        result = Agent._compact_messages(messages, keep_recent=3)

        for i, msg in enumerate(result):
            if msg.get("role") == "tool":
                prev = result[i - 1]
                assert prev.get("role") == "assistant" and "tool_calls" in prev, (
                    f"Orphaned tool message at index {i}"
                )

    def test_no_system_messages_doesnt_crash(self):
        """Compact works even without a system message."""
        messages = [
            _make_user("hello"),
            _make_assistant(tool_calls=[_make_tool_call("tc1", "bash")]),
            _make_tool("tc1", "output"),
            _make_user("thanks"),
        ]

        result = Agent._compact_messages(messages, keep_recent=1)
        # Should not crash, and no orphaned tool messages
        for i, msg in enumerate(result):
            if msg.get("role") == "tool":
                assert i > 0
                assert result[i - 1].get("role") == "assistant" and "tool_calls" in result[i - 1]

    def test_empty_messages_returns_empty(self):
        """Empty message list returns empty."""
        result = Agent._compact_messages([], keep_recent=4)
        assert result == []

    def test_short_message_list_unchanged(self):
        """Messages shorter than keep_recent are returned as-is."""
        messages = [
            _make_system(),
            _make_user("hi"),
            _make_assistant(tool_calls=[_make_tool_call("tc1", "bash")]),
            _make_tool("tc1", "output"),
        ]
        result = Agent._compact_messages(messages, keep_recent=10)
        assert result == messages

    def test_assistant_with_tool_calls_but_missing_tool_response(self):
        """Assistant with tool_calls but no tool response — assistant is kept but incomplete sequence is handled."""
        messages = [
            _make_system(),
            _make_user("do something"),
            _make_assistant(tool_calls=[_make_tool_call("tc1", "bash")]),
            # No tool response follows — edge case but shouldn't crash
            _make_user("next question"),
            _make_assistant("answer"),
        ]

        result = Agent._compact_messages(messages, keep_recent=2)
        # Should not crash
        assert len(result) > 0
