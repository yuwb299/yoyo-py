"""Tests for the /compact REPL command.

The /compact command manually triggers context compaction, summarizing
old messages and keeping system prompt + recent messages.
"""

import pytest
from unittest.mock import patch, MagicMock
from src.agent import Agent, AgentState
from src.repl import load_system_prompt


class TestCompactCommand:
    """Test that /compact properly compacts the agent's message history."""

    def test_compact_reduces_message_count(self):
        """When there are many messages, /compact should reduce the count."""
        agent = Agent(
            provider=MagicMock(),
            system_prompt="You are helpful.",
            tools={},
            tool_schemas=[],
        )
        # Add 20 user/assistant pairs (40 messages + 1 system = 41 total)
        for i in range(20):
            agent.state.messages.append({"role": "user", "content": f"Question {i}" * 50})
            agent.state.messages.append({"role": "assistant", "content": f"Answer {i}" * 50})

        old_count = len(agent.state.messages)
        agent.state.messages = Agent._compact_messages(agent.state.messages)
        new_count = len(agent.state.messages)

        # Should be fewer messages now (system + summary + 4 recent = ~6)
        assert new_count < old_count
        # System prompt should be preserved
        assert agent.state.messages[0]["role"] == "system"

    def test_compact_preserves_system_prompt(self):
        """System prompt must survive compaction."""
        agent = Agent(
            provider=MagicMock(),
            system_prompt="You are helpful.",
            tools={},
            tool_schemas=[],
        )
        agent.state.messages.append({"role": "user", "content": "hi"})
        agent.state.messages.append({"role": "assistant", "content": "hello"})

        agent.state.messages = Agent._compact_messages(agent.state.messages)
        assert agent.state.messages[0]["role"] == "system"
        assert agent.state.messages[0]["content"] == "You are helpful."

    def test_compact_on_short_history_is_noop(self):
        """If history is short enough, compact doesn't change anything."""
        agent = Agent(
            provider=MagicMock(),
            system_prompt="You are helpful.",
            tools={},
            tool_schemas=[],
        )
        agent.state.messages.append({"role": "user", "content": "hi"})
        agent.state.messages.append({"role": "assistant", "content": "hello"})

        old = list(agent.state.messages)
        agent.state.messages = Agent._compact_messages(agent.state.messages)

        assert agent.state.messages == old

    def test_compact_summary_content(self):
        """Compacted messages should include a summary of old messages."""
        agent = Agent(
            provider=MagicMock(),
            system_prompt="You are helpful.",
            tools={},
            tool_schemas=[],
        )
        # 10 messages (more than keep_recent=4)
        for i in range(5):
            agent.state.messages.append({"role": "user", "content": f"Question {i}"})
            agent.state.messages.append({"role": "assistant", "content": f"Answer {i}"})

        agent.state.messages = Agent._compact_messages(agent.state.messages)

        # Second message should be the summary
        assert "Summary" in agent.state.messages[1]["content"]

    def test_compact_keeps_recent_messages(self):
        """The last 4 non-system messages should be preserved verbatim."""
        agent = Agent(
            provider=MagicMock(),
            system_prompt="You are helpful.",
            tools={},
            tool_schemas=[],
        )
        for i in range(10):
            agent.state.messages.append({"role": "user", "content": f"Q{i}"})
            agent.state.messages.append({"role": "assistant", "content": f"A{i}"})

        agent.state.messages = Agent._compact_messages(agent.state.messages)

        # Last 4 messages should be the most recent
        recent = agent.state.messages[-4:]
        contents = [m["content"] for m in recent]
        # Most recent user+assistant pair should be Q9/A9
        assert "Q9" in contents
        assert "A9" in contents
