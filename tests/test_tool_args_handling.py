"""Tests for graceful handling of tool calls with missing or invalid arguments."""

import asyncio
import pytest
from unittest.mock import MagicMock

from src.agent import Agent, AgentEvent
from src.provider import Usage


def _make_chunk(content=None, tool_calls=None, finish_reason=None, usage=None):
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
    tc = MagicMock()
    tc.index = index
    tc.id = id
    tc.function = MagicMock()
    tc.function.name = name
    tc.function.arguments = arguments
    return tc


def _mock_parse_usage(response):
    if hasattr(response, "usage") and response.usage:
        return Usage(
            input_tokens=getattr(response.usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(response.usage, "completion_tokens", 0) or 0,
        )
    return Usage()


async def _collect_events(agent, user_input):
    events = []
    async for event in agent.prompt(user_input):
        events.append(event)
    return events


class TestToolCallMissingArgs:
    def test_tool_call_with_empty_args_missing_required(self):
        """Tool call with empty JSON {} for a tool that requires 'command' should give a helpful error, not crash."""
        tc_delta = _make_tool_call_delta(
            index=0, id="call_empty", name="bash", arguments='{}'
        )
        tool_call_chunks = [
            _make_chunk(tool_calls=[tc_delta]),
            _make_chunk(finish_reason="tool_calls"),
        ]

        text_chunks = [
            _make_chunk(content="I see the command was missing."),
            _make_usage_chunk(),
        ]

        mock_provider = MagicMock()
        mock_provider.chat.side_effect = [iter(tool_call_chunks), iter(text_chunks)]
        mock_provider.parse_usage = _mock_parse_usage

        from src.tools import TOOL_FUNCTIONS
        from src.tools import TOOL_SCHEMAS
        agent = Agent(
            provider=mock_provider,
            system_prompt="test",
            tools={"bash": TOOL_FUNCTIONS["bash"]},
            tool_schemas=[s for s in TOOL_SCHEMAS if s["function"]["name"] == "bash"],
        )

        events = asyncio.get_event_loop().run_until_complete(_collect_events(agent, "run bash"))

        tool_end_events = [(e, d) for e, d in events if e == AgentEvent.TOOL_END]
        assert len(tool_end_events) == 1
        # Should get an error message, not a crash
        assert tool_end_events[0][1]["is_error"]
        assert "command" in tool_end_events[0][1]["output"].lower() or "missing" in tool_end_events[0][1]["output"].lower() or "required" in tool_end_events[0][1]["output"].lower()

    def test_tool_call_with_none_arguments(self):
        """Tool call with None arguments (some APIs send this) should not crash."""
        tc_delta = _make_tool_call_delta(
            index=0, id="call_none", name="list_files", arguments=None
        )
        tool_call_chunks = [
            _make_chunk(tool_calls=[tc_delta]),
            _make_chunk(finish_reason="tool_calls"),
        ]

        text_chunks = [
            _make_chunk(content="Here are the files."),
            _make_usage_chunk(),
        ]

        mock_provider = MagicMock()
        mock_provider.chat.side_effect = [iter(tool_call_chunks), iter(text_chunks)]
        mock_provider.parse_usage = _mock_parse_usage

        from src.tools import TOOL_FUNCTIONS
        agent = Agent(
            provider=mock_provider,
            system_prompt="test",
            tools={"list_files": TOOL_FUNCTIONS["list_files"]},
            tool_schemas=[{"type": "function", "function": {"name": "list_files", "parameters": {}}}],
        )

        # Should not crash — None args should be handled
        events = asyncio.get_event_loop().run_until_complete(_collect_events(agent, "list files"))
        tool_start_events = [(e, d) for e, d in events if e == AgentEvent.TOOL_START]
        assert len(tool_start_events) == 1
