"""Tests for auto-compact integration into the agent loop.

The auto-compact feature was implemented as static methods but never
called from the agent loop. These tests verify that compaction is
automatically triggered when context grows too long.
"""

import asyncio
import pytest
from unittest.mock import MagicMock, patch
from src.agent import Agent, AgentEvent
from src.provider import Usage


def _make_chunk(content=None, tool_calls=None, finish_reason=None, usage=None):
    """Create a mock stream chunk that mimics OpenAI's ChatCompletionChunk."""
    delta = MagicMock()
    delta.content = content
    delta.tool_calls = tool_calls

    choice = MagicMock()
    choice.delta = delta
    choice.finish_reason = finish_reason

    chunk = MagicMock()
    chunk.choices = [choice]
    chunk.usage = usage
    return chunk


def _make_usage_chunk(input_tokens=0, output_tokens=0):
    """Create a chunk with usage info."""
    usage_obj = MagicMock()
    usage_obj.prompt_tokens = input_tokens
    usage_obj.completion_tokens = output_tokens

    delta = MagicMock()
    delta.content = None
    delta.tool_calls = None

    choice = MagicMock()
    choice.delta = delta
    choice.finish_reason = "stop"

    chunk = MagicMock()
    chunk.choices = [choice]
    chunk.usage = usage_obj
    return chunk


async def _collect_events(agent, user_input):
    """Collect all events from an async generator into a list."""
    events = []
    async for event in agent.prompt(user_input):
        events.append(event)
    return events


def _mock_parse_usage(response):
    """Standalone version of GLMProvider.parse_usage for testing."""
    if hasattr(response, "usage") and response.usage:
        return Usage(
            input_tokens=getattr(response.usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(response.usage, "completion_tokens", 0) or 0,
        )
    return Usage()


class TestAutoCompactIntegration:
    """Test that auto-compact is triggered during the agent loop."""

    def test_compact_triggered_on_long_conversation(self):
        """When conversation exceeds token budget, compact is called before next API call."""
        agent = Agent(
            provider=MagicMock(),
            system_prompt="You are helpful.",
        )
        # Simulate a long conversation by adding many messages
        for i in range(50):
            agent.state.messages.append({"role": "user", "content": "X" * 1000})
            agent.state.messages.append({"role": "assistant", "content": "Y" * 1000})

        original_count = len(agent.state.messages)

        # Manually trigger compact check (simulating what the loop does)
        if Agent._should_compact(agent.state.messages, max_tokens=10000):
            agent.state.messages = Agent._compact_messages(agent.state.messages, keep_recent=4)

        # Messages should have been compacted
        assert len(agent.state.messages) < original_count
        # System prompt should still be first
        assert agent.state.messages[0]["role"] == "system"

    def test_compact_not_triggered_on_short_conversation(self):
        """Short conversations should not trigger compaction."""
        agent = Agent(
            provider=MagicMock(),
            system_prompt="You are helpful.",
        )
        agent.state.messages.append({"role": "user", "content": "Hello"})
        agent.state.messages.append({"role": "assistant", "content": "Hi"})

        original_count = len(agent.state.messages)
        assert not Agent._should_compact(agent.state.messages, max_tokens=100000)
        # No compaction should happen
        result = Agent._compact_messages(agent.state.messages, keep_recent=4)
        assert len(result) == original_count

    def test_compact_preserves_system_prompt_after_multiple_compacts(self):
        """System prompt must survive multiple compaction cycles."""
        messages = [{"role": "system", "content": "Important system prompt"}]
        for i in range(10):
            messages.append({"role": "user", "content": f"Question {i}: " + "X" * 500})
            messages.append({"role": "assistant", "content": f"Answer {i}: " + "Y" * 500})

        # Compact once
        result1 = Agent._compact_messages(messages, keep_recent=4)
        assert result1[0]["role"] == "system"
        assert result1[0]["content"] == "Important system prompt"

        # Compact again
        result2 = Agent._compact_messages(result1, keep_recent=4)
        assert result2[0]["role"] == "system"
        assert result2[0]["content"] == "Important system prompt"

    def test_compact_summary_is_not_too_long(self):
        """Compacted summary should be shorter than the original messages."""
        messages = [{"role": "system", "content": "System"}]
        for i in range(20):
            messages.append({"role": "user", "content": "A" * 500})
            messages.append({"role": "assistant", "content": "B" * 500})

        result = Agent._compact_messages(messages, keep_recent=4)
        original_chars = sum(len(m.get("content", "")) for m in messages)
        result_chars = sum(len(m.get("content", "")) for m in result)
        assert result_chars < original_chars


class TestAgentCompactHook:
    """Test that the agent loop actually calls _should_compact."""

    def test_prompt_calls_compact_check(self):
        """The prompt() method should check if compaction is needed before API call."""
        chunks = [
            _make_chunk(content="Hello!"),
            _make_usage_chunk(input_tokens=10, output_tokens=5),
        ]

        mock_provider = MagicMock()
        mock_provider.chat.return_value = iter(chunks)
        mock_provider.parse_usage = _mock_parse_usage

        agent = Agent(provider=mock_provider, system_prompt="System")

        with patch.object(Agent, "_should_compact", return_value=False) as mock_should:
            events = asyncio.get_event_loop().run_until_complete(
                _collect_events(agent, "Hi")
            )
            # _should_compact should have been called at least once
            mock_should.assert_called()

    def test_prompt_compacts_when_needed(self):
        """When _should_compact returns True, compaction should occur during prompt."""
        chunks = [
            _make_chunk(content="Hello!"),
            _make_usage_chunk(input_tokens=10, output_tokens=5),
        ]

        mock_provider = MagicMock()
        mock_provider.chat.return_value = iter(chunks)
        mock_provider.parse_usage = _mock_parse_usage

        agent = Agent(provider=mock_provider, system_prompt="System")

        # Pre-load messages to make it long
        for i in range(20):
            agent.state.messages.append({"role": "user", "content": "X" * 500})
            agent.state.messages.append({"role": "assistant", "content": "Y" * 500})

        msg_count_before = len(agent.state.messages)

        # Force compaction on
        with patch.object(Agent, "_should_compact", return_value=True):
            events = asyncio.get_event_loop().run_until_complete(
                _collect_events(agent, "Hi")
            )

        # Messages should have been compacted (fewer than before + the new user msg)
        assert len(agent.state.messages) < msg_count_before + 1
