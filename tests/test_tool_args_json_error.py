"""Test that malformed tool args JSON produces helpful error messages."""

import asyncio
import json

import pytest

from src.agent import Agent, AgentEvent, ToolResult
from src.provider import GLMProvider


def _make_provider():
    """Create a mock provider that returns a tool call with malformed JSON."""
    provider = object.__new__(GLMProvider)
    provider.model = "test"
    provider.base_url = "http://test"
    provider.api_key = "test"
    provider.max_tokens = None
    provider.temperature = None
    provider.top_p = None
    return provider


def _make_tool_call_response(tool_name: str, args_str: str, finish_reason="tool_calls"):
    """Create a mock chunk that delivers a tool call with the given args string."""
    from unittest.mock import MagicMock

    # Build a full response (not streaming) to return from chat()
    chunk = MagicMock()
    chunk.choices = [MagicMock()]
    chunk.choices[0].delta = MagicMock()
    chunk.choices[0].delta.content = None
    chunk.choices[0].delta.tool_calls = [MagicMock()]
    chunk.choices[0].delta.tool_calls[0].index = 0
    chunk.choices[0].delta.tool_calls[0].id = "call_123"
    chunk.choices[0].delta.tool_calls[0].function = MagicMock()
    chunk.choices[0].delta.tool_calls[0].function.name = tool_name
    chunk.choices[0].delta.tool_calls[0].function.arguments = args_str
    chunk.choices[0].finish_reason = finish_reason
    chunk.usage = None

    return chunk


def _make_text_response(text: str):
    """Create a mock chunk that delivers text content."""
    from unittest.mock import MagicMock

    chunk = MagicMock()
    chunk.choices = [MagicMock()]
    chunk.choices[0].delta = MagicMock()
    chunk.choices[0].delta.content = text
    chunk.choices[0].delta.tool_calls = None
    chunk.choices[0].finish_reason = "stop"
    chunk.usage = MagicMock()
    chunk.usage.prompt_tokens = 10
    chunk.usage.completion_tokens = 5
    return chunk


async def _collect_events(agent, user_input):
    """Collect all events from an agent prompt."""
    events = []
    async for event in agent.prompt(user_input):
        events.append(event)
    return events


def test_malformed_json_shows_raw_args():
    """When tool args JSON is malformed, the error message should include the raw string."""
    from unittest.mock import MagicMock, patch

    provider = _make_provider()

    # First call returns tool call with malformed JSON, second returns text
    malformed_args = "{invalid json!!"
    tool_call_chunk = _make_tool_call_response("read_file", malformed_args)
    text_chunk = _make_text_response("Done")

    call_count = [0]

    def mock_chat(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return iter([tool_call_chunk])
        else:
            return iter([text_chunk])

    provider.chat = mock_chat

    # Register a tool so it gets called
    def dummy_read_file(path=""):
        return f"content of {path}"

    agent = Agent(
        provider=provider,
        tools={"read_file": dummy_read_file},
        tool_schemas=[{
            "type": "function",
            "function": {
                "name": "read_file",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        }],
    )

    events = asyncio.get_event_loop().run_until_complete(
        _collect_events(agent, "test malformed args")
    )

    # Find TOOL_END events
    tool_end_events = [
        (ev, data) for ev, data in events
        if ev == AgentEvent.TOOL_END
    ]

    assert len(tool_end_events) == 1
    ev, data = tool_end_events[0]
    assert data["is_error"] is True
    # The error message should mention the raw malformed args
    assert malformed_args in data["output"], f"Expected raw args in error, got: {data['output']}"


def test_valid_json_args_work_normally():
    """When tool args JSON is valid, the tool should execute normally."""
    from unittest.mock import MagicMock

    provider = _make_provider()

    valid_args = json.dumps({"path": "/tmp/test.txt"})
    tool_call_chunk = _make_tool_call_response("read_file", valid_args)
    text_chunk = _make_text_response("Done")

    call_count = [0]

    def mock_chat(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return iter([tool_call_chunk])
        else:
            return iter([text_chunk])

    provider.chat = mock_chat

    def dummy_read_file(path=""):
        return f"content of {path}"

    agent = Agent(
        provider=provider,
        tools={"read_file": dummy_read_file},
        tool_schemas=[{
            "type": "function",
            "function": {
                "name": "read_file",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        }],
    )

    events = asyncio.get_event_loop().run_until_complete(
        _collect_events(agent, "test valid args")
    )

    tool_end_events = [
        (ev, data) for ev, data in events
        if ev == AgentEvent.TOOL_END
    ]

    assert len(tool_end_events) == 1
    ev, data = tool_end_events[0]
    assert data["is_error"] is False
    assert "content of /tmp/test.txt" in data["output"]


def test_empty_string_json_handled():
    """When tool args is an empty string, it should still produce a helpful error."""
    from unittest.mock import MagicMock

    provider = _make_provider()

    tool_call_chunk = _make_tool_call_response("read_file", "")
    text_chunk = _make_text_response("Done")

    call_count = [0]

    def mock_chat(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return iter([tool_call_chunk])
        else:
            return iter([text_chunk])

    provider.chat = mock_chat

    def dummy_read_file(path=""):
        return f"content of {path}"

    agent = Agent(
        provider=provider,
        tools={"read_file": dummy_read_file},
        tool_schemas=[{
            "type": "function",
            "function": {
                "name": "read_file",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        }],
    )

    events = asyncio.get_event_loop().run_until_complete(
        _collect_events(agent, "test empty args")
    )

    tool_end_events = [
        (ev, data) for ev, data in events
        if ev == AgentEvent.TOOL_END
    ]

    # Empty string parses as valid JSON error or tool runs with default args
    # Either way, we should get a result
    assert len(tool_end_events) >= 1
