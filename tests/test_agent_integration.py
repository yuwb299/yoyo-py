"""Integration tests for the agent loop — test the full tool-calling cycle with a mocked provider."""

import asyncio
import json
import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

from src.agent import Agent, AgentEvent, ToolResult
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
    """Create a chunk with usage info (typically the last chunk)."""
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


def _make_tool_call_delta(index, id=None, name=None, arguments=None):
    """Create a mock tool call delta."""
    tc = MagicMock()
    tc.index = index
    tc.id = id
    tc.function = MagicMock()
    tc.function.name = name
    tc.function.arguments = arguments
    return tc


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


class TestAgentLoopIntegration:
    """Test the full agent loop: LLM response → tool execution → LLM response → done."""

    def test_text_only_response(self):
        """Agent receives text from LLM, no tool calls → DONE."""
        chunks = [
            _make_chunk(content="Hello, "),
            _make_chunk(content="world!"),
            _make_usage_chunk(input_tokens=10, output_tokens=5),
        ]

        mock_provider = MagicMock()
        mock_provider.chat.return_value = iter(chunks)
        mock_provider.parse_usage = _mock_parse_usage

        agent = Agent(provider=mock_provider, system_prompt="test")
        events = asyncio.get_event_loop().run_until_complete(_collect_events(agent, "hi"))

        # Should get TEXT deltas and DONE
        text_events = [(e, d) for e, d in events if e == AgentEvent.TEXT]
        done_events = [(e, d) for e, d in events if e == AgentEvent.DONE]

        assert len(text_events) == 2
        assert text_events[0][1] == "Hello, "
        assert text_events[1][1] == "world!"
        assert len(done_events) == 1
        # Usage accumulates across all chunks; at least what the usage chunk reported
        assert done_events[0][1].input_tokens >= 10

    def test_tool_call_and_response(self):
        """Agent calls a tool, gets result, LLM responds with text."""
        # First LLM response: tool call
        tc_delta = _make_tool_call_delta(
            index=0, id="call_123", name="bash", arguments='{"command": "echo hi"}'
        )
        tool_call_chunks = [
            _make_chunk(tool_calls=[tc_delta]),
            _make_chunk(finish_reason="tool_calls"),
        ]

        # Second LLM response: text after tool result
        text_chunks = [
            _make_chunk(content="The command output is 'hi'"),
            _make_usage_chunk(input_tokens=20, output_tokens=10),
        ]

        mock_provider = MagicMock()
        mock_provider.chat.side_effect = [iter(tool_call_chunks), iter(text_chunks)]
        mock_provider.parse_usage = _mock_parse_usage

        # Register the bash tool
        from src.tools import tool_bash
        agent = Agent(
            provider=mock_provider,
            system_prompt="test",
            tools={"bash": tool_bash},
            tool_schemas=[{"type": "function", "function": {"name": "bash", "parameters": {}}}],
        )

        events = asyncio.get_event_loop().run_until_complete(_collect_events(agent, "run echo hi"))

        tool_start_events = [(e, d) for e, d in events if e == AgentEvent.TOOL_START]
        tool_end_events = [(e, d) for e, d in events if e == AgentEvent.TOOL_END]
        done_events = [(e, d) for e, d in events if e == AgentEvent.DONE]

        assert len(tool_start_events) == 1
        assert tool_start_events[0][1]["name"] == "bash"
        assert len(tool_end_events) == 1
        assert not tool_end_events[0][1]["is_error"]
        assert "hi" in tool_end_events[0][1]["output"]
        assert len(done_events) == 1

    def test_unknown_tool_call(self):
        """Agent calls an unknown tool → error result fed back to LLM."""
        tc_delta = _make_tool_call_delta(
            index=0, id="call_456", name="nonexistent_tool", arguments='{}'
        )
        tool_call_chunks = [
            _make_chunk(tool_calls=[tc_delta]),
            _make_chunk(finish_reason="tool_calls"),
        ]

        text_chunks = [
            _make_chunk(content="Sorry, I can't do that."),
            _make_usage_chunk(input_tokens=5, output_tokens=5),
        ]

        mock_provider = MagicMock()
        mock_provider.chat.side_effect = [iter(tool_call_chunks), iter(text_chunks)]
        mock_provider.parse_usage = _mock_parse_usage

        agent = Agent(provider=mock_provider, system_prompt="test")
        events = asyncio.get_event_loop().run_until_complete(_collect_events(agent, "use unknown tool"))

        tool_end_events = [(e, d) for e, d in events if e == AgentEvent.TOOL_END]
        assert len(tool_end_events) == 1
        assert tool_end_events[0][1]["is_error"]
        assert "Unknown tool" in tool_end_events[0][1]["output"]

    def test_tool_execution_error(self):
        """Tool function raises an exception → error result."""
        def failing_tool(**kwargs):
            raise RuntimeError("Something broke")

        tc_delta = _make_tool_call_delta(
            index=0, id="call_789", name="fail_tool", arguments='{}'
        )
        tool_call_chunks = [
            _make_chunk(tool_calls=[tc_delta]),
            _make_chunk(finish_reason="tool_calls"),
        ]

        text_chunks = [
            _make_chunk(content="I see the tool failed."),
            _make_usage_chunk(),
        ]

        mock_provider = MagicMock()
        mock_provider.chat.side_effect = [iter(tool_call_chunks), iter(text_chunks)]
        mock_provider.parse_usage = _mock_parse_usage

        agent = Agent(
            provider=mock_provider,
            system_prompt="test",
            tools={"fail_tool": failing_tool},
            tool_schemas=[{"type": "function", "function": {"name": "fail_tool", "parameters": {}}}],
        )

        events = asyncio.get_event_loop().run_until_complete(_collect_events(agent, "use failing tool"))
        tool_end_events = [(e, d) for e, d in events if e == AgentEvent.TOOL_END]
        assert len(tool_end_events) == 1
        assert tool_end_events[0][1]["is_error"]
        assert "Something broke" in tool_end_events[0][1]["output"]

    def test_api_error(self):
        """Provider raises an exception → ERROR event."""
        mock_provider = MagicMock()
        mock_provider.chat.side_effect = Exception("API is down")
        mock_provider.parse_usage = _mock_parse_usage

        agent = Agent(provider=mock_provider, system_prompt="test")
        events = asyncio.get_event_loop().run_until_complete(_collect_events(agent, "hello"))

        error_events = [(e, d) for e, d in events if e == AgentEvent.ERROR]
        assert len(error_events) == 1
        assert "API is down" in error_events[0][1]

    def test_interrupt_during_stream(self):
        """Interrupt during streaming should set the _interrupted flag."""
        chunks = [
            _make_chunk(content="Partial text..."),
        ]

        mock_provider = MagicMock()
        mock_provider.chat.return_value = iter(chunks)
        mock_provider.parse_usage = _mock_parse_usage

        agent = Agent(provider=mock_provider, system_prompt="test")

        # We can't easily interrupt mid-stream in a sync test,
        # but we can test the interrupt method directly
        agent.interrupt()
        assert agent._interrupted

    def test_max_tool_rounds_exceeded(self):
        """If LLM keeps calling tools, we should hit the max rounds safety limit."""
        # Each call returns a tool call — never terminates
        tc_delta = _make_tool_call_delta(
            index=0, id="call_loop", name="bash", arguments='{"command": "echo loop"}'
        )
        loop_chunks = [
            _make_chunk(tool_calls=[tc_delta]),
            _make_chunk(finish_reason="tool_calls"),
        ]

        mock_provider = MagicMock()
        # Always return a fresh iterator for tool calls — infinite loop
        mock_provider.chat.side_effect = lambda *a, **kw: iter(loop_chunks)
        mock_provider.parse_usage = _mock_parse_usage

        from src.tools import tool_bash
        agent = Agent(
            provider=mock_provider,
            system_prompt="test",
            tools={"bash": tool_bash},
            tool_schemas=[{"type": "function", "function": {"name": "bash", "parameters": {}}}],
            max_tool_rounds=3,  # Low limit for testing
        )

        events = asyncio.get_event_loop().run_until_complete(_collect_events(agent, "keep calling tools"))

        error_events = [(e, d) for e, d in events if e == AgentEvent.ERROR]
        assert len(error_events) == 1
        assert "Exceeded max tool rounds" in error_events[0][1]

    def test_malformed_tool_args(self):
        """Tool call with invalid JSON arguments should use empty dict, not crash."""
        tc_delta = _make_tool_call_delta(
            index=0, id="call_bad", name="bash", arguments='{not valid json'
        )
        tool_call_chunks = [
            _make_chunk(tool_calls=[tc_delta]),
            _make_chunk(finish_reason="tool_calls"),
        ]

        text_chunks = [
            _make_chunk(content="OK"),
            _make_usage_chunk(),
        ]

        mock_provider = MagicMock()
        mock_provider.chat.side_effect = [iter(tool_call_chunks), iter(text_chunks)]
        mock_provider.parse_usage = _mock_parse_usage

        from src.tools import tool_bash
        agent = Agent(
            provider=mock_provider,
            system_prompt="test",
            tools={"bash": tool_bash},
            tool_schemas=[{"type": "function", "function": {"name": "bash", "parameters": {}}}],
        )

        # Malformed JSON now produces a TOOL_END error directly (no TOOL_START)
        events = asyncio.get_event_loop().run_until_complete(_collect_events(agent, "bad args"))
        tool_end_events = [(e, d) for e, d in events if e == AgentEvent.TOOL_END]
        assert len(tool_end_events) == 1
        assert tool_end_events[0][1]["is_error"] is True
        assert "Malformed JSON" in tool_end_events[0][1]["output"]

    def test_conversation_state_preserved(self):
        """Messages accumulate correctly across tool rounds."""
        tc_delta = _make_tool_call_delta(
            index=0, id="call_1", name="bash", arguments='{"command": "echo test"}'
        )
        tool_call_chunks = [
            _make_chunk(tool_calls=[tc_delta]),
            _make_chunk(finish_reason="tool_calls"),
        ]

        text_chunks = [
            _make_chunk(content="Done!"),
            _make_usage_chunk(),
        ]

        mock_provider = MagicMock()
        mock_provider.chat.side_effect = [iter(tool_call_chunks), iter(text_chunks)]
        mock_provider.parse_usage = _mock_parse_usage

        from src.tools import tool_bash
        agent = Agent(
            provider=mock_provider,
            system_prompt="test",
            tools={"bash": tool_bash},
            tool_schemas=[{"type": "function", "function": {"name": "bash", "parameters": {}}}],
        )

        asyncio.get_event_loop().run_until_complete(_collect_events(agent, "run echo test"))

        # Check message history: system, user, assistant (with tool_calls), tool, assistant (text)
        msgs = agent.state.messages
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert msgs[2]["role"] == "assistant"
        assert "tool_calls" in msgs[2]
        assert msgs[3]["role"] == "tool"
        assert msgs[4]["role"] == "assistant"
        assert msgs[4]["content"] == "Done!"
