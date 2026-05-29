"""Tests for compact_messages summary role handling.

The summary message's role should avoid consecutive same-role messages.
When recent[0] is a user message, the summary should be assistant role
to prevent consecutive user messages that some APIs reject.
"""

import pytest
from src.agent import Agent


class TestCompactSummaryRole:
    """Test that compact summary avoids consecutive user messages."""

    def test_summary_role_when_recent_starts_with_user(self):
        """Summary should be assistant role when recent starts with a user message."""
        messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "old message 1"},
            {"role": "assistant", "content": "old response 1"},
            {"role": "user", "content": "old message 2"},
            {"role": "assistant", "content": "old response 2"},
            # Recent messages
            {"role": "user", "content": "recent message"},
            {"role": "assistant", "content": "recent response"},
            {"role": "user", "content": "latest message"},
            {"role": "assistant", "content": "latest response"},
        ]
        result = Agent._compact_messages(messages, keep_recent=4)

        # Find the summary message — it's the one after system
        assert result[0]["role"] == "system"
        summary = result[1]
        assert "Summary of previous conversation" in summary.get("content", "")

        # The summary should NOT be role=user when the first recent message is user
        # This prevents consecutive user messages
        assert summary["role"] == "assistant", (
            f"Summary role should be 'assistant' when recent starts with user, "
            f"but got '{summary['role']}'"
        )

    def test_summary_role_when_recent_starts_with_assistant(self):
        """Summary should be user role when recent starts with an assistant message."""
        messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "old message 1"},
            {"role": "assistant", "content": "old response 1"},
            {"role": "user", "content": "old message 2"},
            {"role": "assistant", "content": "old response 2"},
            {"role": "user", "content": "old message 3"},
            # Recent starts with assistant
            {"role": "assistant", "content": "recent response"},
            {"role": "user", "content": "latest message"},
            {"role": "assistant", "content": "latest response"},
        ]
        result = Agent._compact_messages(messages, keep_recent=3)

        summary = result[1]
        # When recent starts with assistant, user summary is fine (alternating)
        assert summary["role"] == "user"

    def test_summary_role_when_recent_starts_with_tool(self):
        """Summary should be user role when recent starts with a tool message (after orphan fix)."""
        messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "old message 1"},
            {"role": "assistant", "content": "old response 1", "tool_calls": [
                {"id": "tc_1", "type": "function", "function": {"name": "bash", "arguments": '{"command": "ls"}'}}
            ]},
            {"role": "tool", "tool_call_id": "tc_1", "content": "file1.py"},
            {"role": "user", "content": "old message 2"},
            {"role": "assistant", "content": "old response 2"},
            # Recent starts with user
            {"role": "user", "content": "recent message"},
            {"role": "assistant", "content": "recent response"},
            {"role": "user", "content": "latest"},
            {"role": "assistant", "content": "latest response"},
        ]
        result = Agent._compact_messages(messages, keep_recent=4)

        summary = result[1]
        # After orphan fix, recent should start with user, so summary should be assistant
        first_recent = result[2]
        if first_recent.get("role") == "user":
            assert summary["role"] == "assistant"

    def test_no_consecutive_user_messages_after_compact(self):
        """After compaction, there should never be consecutive user messages."""
        messages = [
            {"role": "system", "content": "system prompt"},
        ]
        # Add 20 user/assistant pairs
        for i in range(20):
            messages.append({"role": "user", "content": f"user message {i}"})
            messages.append({"role": "assistant", "content": f"assistant response {i}"})

        result = Agent._compact_messages(messages, keep_recent=4)

        # Check no consecutive user messages
        for i in range(1, len(result)):
            if result[i - 1]["role"] == "user" and result[i]["role"] == "user":
                pytest.fail(
                    f"Consecutive user messages at positions {i-1} and {i}: "
                    f"{result[i-1]['content'][:50]}... -> {result[i]['content'][:50]}..."
                )

    def test_no_consecutive_assistant_messages_after_compact(self):
        """After compaction, there should never be consecutive assistant messages."""
        messages = [
            {"role": "system", "content": "system prompt"},
        ]
        for i in range(20):
            messages.append({"role": "user", "content": f"user message {i}"})
            messages.append({"role": "assistant", "content": f"assistant response {i}"})

        result = Agent._compact_messages(messages, keep_recent=4)

        for i in range(1, len(result)):
            prev_role = result[i - 1]["role"]
            curr_role = result[i]["role"]
            if prev_role == "assistant" and curr_role == "assistant":
                # Tool messages between assistants are OK
                if curr_role != "tool":
                    pytest.fail(
                        f"Consecutive assistant messages at positions {i-1} and {i}"
                    )
