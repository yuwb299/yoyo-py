"""Tests for always-validating compacted messages (not just in verbose mode).

This test validates that _compact_messages always produces valid conversation
structure, and that the agent loop always validates after compaction — not
just in verbose mode. This was a reliability gap: the compact function has had
3 bugs in 37 days (Days 5, 18, 37), and silent corruption is worse than a
visible warning.
"""

import pytest
from src.agent import Agent


class TestCompactAlwaysValidates:
    """Compact should always produce valid messages, validated post-compact."""

    def test_compact_produces_valid_messages_basic(self):
        """Basic compaction should produce no validation issues."""
        messages = [
            {"role": "system", "content": "You are a helper."},
        ]
        # Add 20 user/assistant exchanges
        for i in range(20):
            messages.append({"role": "user", "content": f"Question {i}" * 50})
            messages.append({"role": "assistant", "content": f"Answer {i}" * 50})

        result = Agent._compact_messages(messages, keep_recent=4)
        issues = Agent._validate_messages(result)
        assert issues == [], f"Compacted messages have issues: {issues}"

    def test_compact_with_tool_calls_produces_valid_messages(self):
        """Compaction with tool calls should produce no validation issues."""
        messages = [
            {"role": "system", "content": "You are a helper."},
            {"role": "user", "content": "Read the file"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "tc_1", "type": "function", "function": {"name": "read_file", "arguments": '{"path": "test.txt"}'}}
            ]},
            {"role": "tool", "tool_call_id": "tc_1", "content": "file contents here"},
            {"role": "assistant", "content": "Here's the file contents"},
        ]
        for i in range(10):
            messages.append({"role": "user", "content": f"Question {i}" * 50})
            messages.append({"role": "assistant", "content": f"Answer {i}" * 50})

        result = Agent._compact_messages(messages, keep_recent=4)
        issues = Agent._validate_messages(result)
        assert issues == [], f"Compacted messages have issues: {issues}"

    def test_compact_orphaned_tool_fixup_produces_valid_messages(self):
        """When compaction splits tool sequences, fixup should keep messages valid."""
        messages = [
            {"role": "system", "content": "You are a helper."},
            {"role": "user", "content": "Do stuff"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "tc_1", "type": "function", "function": {"name": "bash", "arguments": '{"command": "ls"}'}}
            ]},
            {"role": "tool", "tool_call_id": "tc_1", "content": "file1.txt\nfile2.txt"},
            {"role": "user", "content": "Read file1"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "tc_2", "type": "function", "function": {"name": "read_file", "arguments": '{"path": "file1.txt"}'}}
            ]},
            {"role": "tool", "tool_call_id": "tc_2", "content": "file contents"},
            {"role": "assistant", "content": "Here are the contents of file1."},
        ]

        # With keep_recent=2, the tool sequence at the boundary gets split
        result = Agent._compact_messages(messages, keep_recent=2)
        issues = Agent._validate_messages(result)
        assert issues == [], f"Compacted messages have issues: {issues}"

    def test_compact_empty_recent_produces_valid_messages(self):
        """When all messages are old, empty recent should still produce valid output."""
        messages = [
            {"role": "system", "content": "You are a helper."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]

        # keep_recent=4 means nothing gets compacted (only 2 non-system msgs)
        result = Agent._compact_messages(messages, keep_recent=4)
        issues = Agent._validate_messages(result)
        assert issues == []

    def test_compact_preserves_no_consecutive_same_role(self):
        """Compacted messages should never have consecutive user or assistant messages."""
        messages = [
            {"role": "system", "content": "You are a helper."},
        ]
        # Create alternating conversation
        for i in range(30):
            messages.append({"role": "user", "content": f"Q{i}" * 30})
            messages.append({"role": "assistant", "content": f"A{i}" * 30})

        result = Agent._compact_messages(messages, keep_recent=6)
        issues = Agent._validate_messages(result)

        # Specifically check for consecutive same-role messages
        for i in range(1, len(result)):
            prev_role = result[i - 1].get("role")
            curr_role = result[i].get("role")
            if prev_role in ("user", "assistant") and curr_role == prev_role:
                pytest.fail(f"Consecutive {curr_role} messages at positions {i-1} and {i}")

    def test_agent_prompt_validates_after_compact_non_verbose(self):
        """Agent.prompt() should validate after compact even without verbose=True."""
        from unittest.mock import MagicMock, patch
        from src.agent import AgentEvent

        # Create agent with non-verbose mode
        agent = Agent(
            provider=MagicMock(),
            system_prompt="You are a helper.",
            tools={},
            tool_schemas=[],
            verbose=False,  # Non-verbose — validation should still happen
        )
        # Set very low compact threshold to force compaction
        agent.state.compact_threshold = 10

        # Add enough messages to trigger compaction
        for i in range(20):
            agent.state.messages.append({"role": "user", "content": f"Q{i}" * 50})
            agent.state.messages.append({"role": "assistant", "content": f"A{i}" * 50})

        # Mock the provider to return a simple response
        mock_chunk = MagicMock()
        mock_chunk.choices = [MagicMock()]
        mock_chunk.choices[0].delta = MagicMock(content="done", tool_calls=None)
        mock_chunk.choices[0].finish_reason = "stop"
        mock_chunk.usage = None

        agent.provider.chat.return_value = iter([mock_chunk])

        # Run the prompt — should not crash and should validate
        import asyncio
        events = []
        async def collect():
            async for event in agent.prompt("test"):
                events.append(event)
        asyncio.get_event_loop().run_until_complete(collect())

        # Check that the messages are still valid after compaction
        issues = Agent._validate_messages(agent.state.messages)
        assert issues == [], f"Messages invalid after compact in non-verbose mode: {issues}"

    def test_compact_large_conversation_stays_valid(self):
        """Large conversations with mixed content types should compact to valid state."""
        messages = [
            {"role": "system", "content": "You are a helper."},
        ]
        for i in range(50):
            messages.append({"role": "user", "content": f"Question {i}" * 20})
            messages.append({"role": "assistant", "content": None, "tool_calls": [
                {"id": f"tc_{i}_1", "type": "function", "function": {"name": "bash", "arguments": f'{{"command": "echo {i}"}}'}}
            ]})
            messages.append({"role": "tool", "tool_call_id": f"tc_{i}_1", "content": f"output {i}"})
            messages.append({"role": "assistant", "content": f"Result {i}" * 20})

        result = Agent._compact_messages(messages, keep_recent=4)
        issues = Agent._validate_messages(result)
        assert issues == [], f"Large conversation compaction has issues: {issues}"
