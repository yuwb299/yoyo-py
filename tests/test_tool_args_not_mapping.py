"""Tests: tool arguments sent as a JSON array (not object) must not crash.

When the LLM emits `"arguments": "[1, 2, 3]"` or `'"hello"'` — valid JSON but
not a JSON object — `json.loads` succeeds and returns a list/str/int. The agent
then does `self.tools[name](**tool_args)`, which raises Python's internal
`TypeError: f() argument after ** must be a mapping, not list`. That message
names neither the tool nor the problem, so the LLM can't recover.

The fix: validate that parsed args is a dict right after json.loads. If not,
surface a clear "must be a JSON object" error naming the tool.
"""

import asyncio
import json

from src.agent import Agent, AgentEvent
from src.provider import GLMProvider
from tests.test_tool_args_json_error import (
    _make_provider,
    _make_tool_call_response,
    _make_text_response,
)


async def _collect_events(agent, user_input):
    events = []
    async for event in agent.prompt(user_input):
        events.append(event)
    return events


def _run(agent, user_input):
    return asyncio.new_event_loop().run_until_complete(_collect_events(agent, user_input))


def _build_agent(args_str: str):
    provider = _make_provider()
    tool_chunk = _make_tool_call_response("read_file", args_str)
    text_chunk = _make_text_response("done")

    calls = {"n": 0}

    def mock_chat(*a, **kw):
        calls["n"] += 1
        return iter([tool_chunk]) if calls["n"] == 1 else iter([text_chunk])

    provider.chat = mock_chat

    def dummy_read_file(path=""):
        return f"content of {path}"

    return Agent(
        provider=provider,
        tools={"read_file": dummy_read_file},
        tool_schemas=[{
            "type": "function",
            "function": {
                "name": "read_file",
                "parameters": {"type": "object",
                               "properties": {"path": {"type": "string"}},
                               "required": ["path"]},
            },
        }],
    )


def _tool_end_outputs(events):
    return [d.get("output", "") for ev, d in events if ev == AgentEvent.TOOL_END]


def test_json_array_args_clear_error():
    """`[1, 2, 3]` must yield an error, not a Python-internal TypeError."""
    agent = _build_agent("[1, 2, 3]")
    events = _run(agent, "test")
    outs = _tool_end_outputs(events)
    assert outs, "expected a TOOL_END event"
    msg = outs[0].lower()
    assert "json object" in msg or "must be" in msg, f"unclear message: {outs[0]}"
    # Must NOT leak the raw Python internal error
    assert "must be a mapping" not in outs[0]
    assert "argument after **" not in outs[0]


def test_json_string_args_clear_error():
    """A bare JSON string `'"hello"'` is not a valid args object."""
    agent = _build_agent(json.dumps("hello"))
    events = _run(agent, "test")
    outs = _tool_end_outputs(events)
    assert outs
    assert "must be a mapping" not in outs[0]
    assert "argument after **" not in outs[0]


def test_json_number_args_clear_error():
    """A bare JSON number is not a valid args object."""
    agent = _build_agent("42")
    events = _run(agent, "test")
    outs = _tool_end_outputs(events)
    assert outs
    assert "must be a mapping" not in outs[0]


def test_json_object_args_still_work():
    """A proper object `{...}` must keep working (regression guard)."""
    agent = _build_agent('{"path": "foo.txt"}')
    events = _run(agent, "test")
    outs = _tool_end_outputs(events)
    assert outs
    assert "content of foo.txt" in outs[0]
    assert "[ERROR]" not in outs[0] and "must be" not in outs[0].lower()


def test_json_null_args_clear_error():
    """A bare JSON `null` parses to None — not a valid args object."""
    agent = _build_agent("null")
    events = _run(agent, "test")
    outs = _tool_end_outputs(events)
    assert outs
    assert "must be a mapping" not in outs[0]
    assert "argument after **" not in outs[0]
