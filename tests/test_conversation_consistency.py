"""Tests for conversation consistency after errors.

When the API fails or streaming errors occur, the agent should leave the
conversation in a valid state — no consecutive same-role messages, no
orphaned tool messages without a preceding assistant.
"""

import asyncio
import json
import pytest
from unittest.mock import MagicMock, patch

from src.agent import Agent, AgentEvent
from src.provider import APIError, Usage


def _collect_events(agent, user_input):
    """Collect all events from agent.prompt() into a list."""
    async def _collect():
        events = []
        async for event in agent.prompt(user_input):
            events.append(event)
        return events
    return asyncio.get_event_loop().run_until_complete(_collect())


def _make_mock_provider():
    """Create a mock provider for testing."""
    provider = MagicMock()
    provider.model = "test-model"
    provider.parse_usage.return_value = Usage()
    return provider


def _make_agent(provider=None):
    """Create an agent with no tools for testing."""
    from src.tools import TOOL_FUNCTIONS, TOOL_SCHEMAS
    p = provider or _make_mock_provider()
    return Agent(
        provider=p,
        system_prompt="test",
        tools=TOOL_FUNCTIONS,
        tool_schemas=TOOL_SCHEMAS,
    )


class TestConversationAfterAPIError:
    """Test that conversation state is valid after API errors."""

    def test_api_error_adds_assistant_message(self):
        """After APIError, conversation should have an assistant message after the user message."""
        provider = _make_mock_provider()
        provider.chat.side_effect = APIError("rate limit", category="rate_limit")

        agent = _make_agent(provider)
        events = _collect_events(agent, "hello")

        # Should have emitted an ERROR event
        error_events = [e for e in events if e[0] == AgentEvent.ERROR]
        assert len(error_events) == 1
        assert "rate limit" in error_events[0][1]

        # Conversation should be: [system, user, assistant(error)]
        msgs = agent.state.messages
        assert len(msgs) == 3
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert msgs[2]["role"] == "assistant"
        assert "error" in msgs[2]["content"].lower() or "rate limit" in msgs[2]["content"].lower()

    def test_unexpected_error_adds_assistant_message(self):
        """After unexpected Exception, conversation should have an assistant message."""
        provider = _make_mock_provider()
        provider.chat.side_effect = RuntimeError("something broke")

        agent = _make_agent(provider)
        events = _collect_events(agent, "hello")

        error_events = [e for e in events if e[0] == AgentEvent.ERROR]
        assert len(error_events) == 1

        msgs = agent.state.messages
        assert len(msgs) == 3
        assert msgs[1]["role"] == "user"
        assert msgs[2]["role"] == "assistant"

    def test_stream_error_adds_assistant_message(self):
        """After stream error, conversation should have an assistant message."""
        provider = _make_mock_provider()

        # Create a stream that raises an error
        def bad_stream(*args, **kwargs):
            raise RuntimeError("stream broke")
            yield  # make it a generator

        provider.chat.return_value = bad_stream()

        agent = _make_agent(provider)
        events = _collect_events(agent, "hello")

        error_events = [e for e in events if e[0] == AgentEvent.ERROR]
        assert len(error_events) == 1

        msgs = agent.state.messages
        assert len(msgs) == 3
        assert msgs[1]["role"] == "user"
        assert msgs[2]["role"] == "assistant"

    def test_max_tool_rounds_adds_assistant_message(self):
        """After exceeding max tool rounds, conversation should have an assistant message."""
        provider = _make_mock_provider()

        call_count = 0

        def make_stream(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            # Return a tool call every time to loop infinitely
            chunk = MagicMock()
            chunk.choices = [MagicMock()]
            chunk.choices[0].delta = MagicMock()
            chunk.choices[0].delta.content = None
            chunk.choices[0].delta.tool_calls = [MagicMock()]
            tc = chunk.choices[0].delta.tool_calls[0]
            tc.index = 0
            tc.id = f"call_{call_count}"
            tc.type = "function"
            tc.function = MagicMock()
            tc.function.name = "bash"
            tc.function.arguments = '{"command": "echo hi"}'

            # Finish with tool_calls
            finish_chunk = MagicMock()
            finish_chunk.choices = [MagicMock()]
            finish_chunk.choices[0].delta = MagicMock()
            finish_chunk.choices[0].delta.content = None
            finish_chunk.choices[0].delta.tool_calls = None
            finish_chunk.choices[0].finish_reason = "tool_calls"
            finish_chunk.usage = None

            yield chunk
            yield finish_chunk

        # Each call to chat() needs a fresh generator
        provider.chat.side_effect = lambda *a, **kw: make_stream()

        agent = _make_agent(provider)
        agent.state.max_tool_rounds = 2  # Very low limit for testing

        events = _collect_events(agent, "keep calling tools")

        # Should have max rounds error
        error_events = [e for e in events if e[0] == AgentEvent.ERROR]
        assert len(error_events) == 1
        assert "max tool rounds" in error_events[0][1].lower()

        # Last message should be an assistant (not a tool)
        msgs = agent.state.messages
        assert msgs[-1]["role"] == "assistant"

    def test_second_prompt_after_error_works(self):
        """After an error, sending a second prompt should still work (valid message sequence)."""
        provider = _make_mock_provider()
        provider.chat.side_effect = APIError("timeout", category="timeout")

        agent = _make_agent(provider)
        _collect_events(agent, "first prompt")

        # Now fix the provider to return a normal response
        def good_stream(*args, **kwargs):
            chunk = MagicMock()
            chunk.choices = [MagicMock()]
            chunk.choices[0].delta = MagicMock()
            chunk.choices[0].delta.content = "I'm back!"
            chunk.choices[0].delta.tool_calls = None
            chunk.choices[0].finish_reason = "stop"
            chunk.usage = MagicMock()
            chunk.usage.prompt_tokens = 10
            chunk.usage.completion_tokens = 5
            chunk.usage.total_tokens = 15
            yield chunk

        provider.chat.side_effect = None
        provider.chat.return_value = good_stream()

        events = _collect_events(agent, "second prompt")

        # Should succeed this time
        done_events = [e for e in events if e[0] == AgentEvent.DONE]
        assert len(done_events) == 1

        # Verify message sequence is valid
        msgs = agent.state.messages
        # [system, user1, assistant(error), user2, assistant(response)]
        assert len(msgs) == 5
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert msgs[2]["role"] == "assistant"
        assert msgs[3]["role"] == "user"
        assert msgs[4]["role"] == "assistant"
