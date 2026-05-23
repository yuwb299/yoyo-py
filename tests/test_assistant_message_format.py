"""Tests for assistant message format — content key must always be present.

Some OpenAI-compatible APIs require the 'content' key on assistant messages,
even when tool_calls are present. Missing 'content' causes API errors.
"""

import asyncio
import json
from unittest.mock import MagicMock, patch

from src.agent import Agent, AgentEvent
from src.provider import GLMProvider, Usage


def _make_chunk(content=None, tool_calls=None, finish_reason=None, usage=None):
    """Create a mock stream chunk."""
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


def _collect_events(agent, user_input):
    """Collect all events from an agent prompt."""
    async def _collect():
        events = []
        async for event in agent.prompt(user_input):
            events.append(event)
        return events
    return asyncio.get_event_loop().run_until_complete(_collect())


class TestAssistantMessageContent:
    """Verify that assistant messages always include 'content' key."""

    def _make_agent(self):
        """Create an agent with a mock provider that returns tool calls."""
        provider = MagicMock(spec=GLMProvider)
        provider.parse_usage = GLMProvider.parse_usage
        agent = Agent(provider=provider, system_prompt="test")
        agent.tools = {"bash": lambda **kw: "ok"}
        agent.tool_schemas = [{}]
        return agent, provider

    def test_assistant_message_with_text_has_content(self):
        """When LLM returns text only, content key should be present."""
        agent, provider = self._make_agent()

        text_chunk = _make_chunk(content="hello", finish_reason="stop")
        provider.chat.return_value = iter([text_chunk])

        _collect_events(agent, "hi")
        msg = agent.state.messages[-1]
        assert "content" in msg
        assert msg["content"] == "hello"

    def test_assistant_message_with_tool_calls_has_content(self):
        """When LLM returns tool calls with no text, content key should still be present.

        Some APIs (e.g. certain OpenAI-compatible endpoints) require 'content' key
        on assistant messages even when tool_calls are present.
        """
        agent, provider = self._make_agent()

        tc_delta = MagicMock()
        tc_delta.index = 0
        tc_delta.id = "call_123"
        tc_delta.function = MagicMock()
        tc_delta.function.name = "bash"
        tc_delta.function.arguments = '{"command": "echo hi"}'

        tool_chunk = _make_chunk(tool_calls=[tc_delta])
        finish_chunk = _make_chunk(finish_reason="tool_calls")

        # First call: tool call; second call: text response
        text_chunk = _make_chunk(content="done", finish_reason="stop")
        provider.chat.side_effect = [iter([tool_chunk, finish_chunk]), iter([text_chunk])]

        _collect_events(agent, "run bash")

        # Find the assistant message with tool_calls
        assistant_msgs = [m for m in agent.state.messages if m.get("role") == "assistant" and "tool_calls" in m]
        assert len(assistant_msgs) == 1
        msg = assistant_msgs[0]
        # The key assertion: content must be present (even if empty/null)
        assert "content" in msg, f"Assistant message missing 'content' key: {msg}"

    def test_assistant_message_with_both_text_and_tool_calls(self):
        """When LLM returns both text and tool calls, content should have the text."""
        agent, provider = self._make_agent()

        text_chunk = _make_chunk(content="let me check")
        tc_delta = MagicMock()
        tc_delta.index = 0
        tc_delta.id = "call_456"
        tc_delta.function = MagicMock()
        tc_delta.function.name = "bash"
        tc_delta.function.arguments = '{"command": "ls"}'

        tool_chunk = _make_chunk(tool_calls=[tc_delta])
        finish_chunk = _make_chunk(finish_reason="tool_calls")

        text_response = _make_chunk(content="here's the list", finish_reason="stop")
        provider.chat.side_effect = [iter([text_chunk, tool_chunk, finish_chunk]), iter([text_response])]

        _collect_events(agent, "list files")

        assistant_msgs = [m for m in agent.state.messages if m.get("role") == "assistant" and "tool_calls" in m]
        assert len(assistant_msgs) == 1
        msg = assistant_msgs[0]
        assert "content" in msg
        assert msg["content"] == "let me check"
