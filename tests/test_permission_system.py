"""Tests for the permission system — confirm before destructive tools execute.

The agent accepts an optional confirm_fn callback. When set, it's called
before executing tools in the "destructive" set (bash, write_file, edit_file).
If confirm_fn returns False, the tool is skipped and a denial message is
sent back to the LLM so it can adapt.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

from src.agent import Agent, AgentEvent
from src.provider import GLMProvider, Usage


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


class TestPermissionSystem:
    """Test that confirm_fn controls tool execution."""

    def test_no_confirm_fn_allows_all_tools(self):
        """Without confirm_fn, all tools execute normally."""
        mock_provider = MagicMock(spec=GLMProvider)
        tc = _make_tool_call_delta(0, id="tc1", name="bash", arguments='{"command": "echo hi"}')
        mock_provider.chat.return_value = iter([
            _make_chunk(tool_calls=[tc], finish_reason="tool_calls"),
        ])

        bash_mock = MagicMock(return_value="hi\n")
        tools = {"bash": bash_mock}
        agent = Agent(provider=mock_provider, tools=tools, tool_schemas=[])

        events = asyncio.get_event_loop().run_until_complete(
            _collect_events(agent, "run a command")
        )

        bash_mock.assert_called_once()
        tool_end_events = [(e, d) for e, d in events if e == AgentEvent.TOOL_END]
        assert len(tool_end_events) == 1
        assert tool_end_events[0][1]["is_error"] is False

    def test_confirm_fn_deny_blocks_tool(self):
        """When confirm_fn returns False, the tool is blocked and denied message sent to LLM."""
        mock_provider = MagicMock(spec=GLMProvider)
        # First call: LLM wants to run bash
        tc1 = _make_tool_call_delta(0, id="tc1", name="bash", arguments='{"command": "rm -rf /"}')
        # Second call: LLM sees denial and responds with text
        mock_provider.chat.side_effect = [
            iter([_make_chunk(tool_calls=[tc1], finish_reason="tool_calls")]),
            iter([_make_chunk(content="I won't do that.", finish_reason="stop")]),
        ]

        bash_mock = MagicMock(return_value="should not be called")
        tools = {"bash": bash_mock}
        # Deny all tools
        agent = Agent(
            provider=mock_provider,
            tools=tools,
            tool_schemas=[],
            confirm_fn=lambda name, args: False,
        )

        events = asyncio.get_event_loop().run_until_complete(
            _collect_events(agent, "delete everything")
        )

        # The bash tool should NOT have been called
        bash_mock.assert_not_called()

        # There should be a TOOL_END with is_error=True (denied)
        tool_end_events = [(e, d) for e, d in events if e == AgentEvent.TOOL_END]
        assert len(tool_end_events) == 1
        assert tool_end_events[0][1]["is_error"] is True
        assert "denied" in tool_end_events[0][1]["output"].lower()

    def test_confirm_fn_allow_executes_tool(self):
        """When confirm_fn returns True, the tool executes normally."""
        mock_provider = MagicMock(spec=GLMProvider)
        tc1 = _make_tool_call_delta(0, id="tc1", name="bash", arguments='{"command": "echo hi"}')
        mock_provider.chat.side_effect = [
            iter([_make_chunk(tool_calls=[tc1], finish_reason="tool_calls")]),
            iter([_make_chunk(content="Done!", finish_reason="stop")]),
        ]

        bash_mock = MagicMock(return_value="hi\n")
        tools = {"bash": bash_mock}
        agent = Agent(
            provider=mock_provider,
            tools=tools,
            tool_schemas=[],
            confirm_fn=lambda name, args: True,
        )

        events = asyncio.get_event_loop().run_until_complete(
            _collect_events(agent, "run a command")
        )

        # The bash tool SHOULD have been called
        bash_mock.assert_called_once()

        tool_end_events = [(e, d) for e, d in events if e == AgentEvent.TOOL_END]
        assert len(tool_end_events) == 1
        assert tool_end_events[0][1]["is_error"] is False

    def test_confirm_fn_only_called_for_destructive_tools(self):
        """confirm_fn is called for bash, write_file, edit_file but NOT read_file, search, list_files."""
        mock_provider = MagicMock(spec=GLMProvider)
        tc1 = _make_tool_call_delta(0, id="tc1", name="read_file", arguments='{"path": "/etc/hosts"}')
        mock_provider.chat.side_effect = [
            iter([_make_chunk(tool_calls=[tc1], finish_reason="tool_calls")]),
            iter([_make_chunk(content="Here's the file.", finish_reason="stop")]),
        ]

        read_mock = MagicMock(return_value="file contents")
        tools = {"read_file": read_mock}

        confirm_calls = []
        def track_confirm(name, args):
            confirm_calls.append(name)
            return True

        agent = Agent(
            provider=mock_provider,
            tools=tools,
            tool_schemas=[],
            confirm_fn=track_confirm,
        )

        asyncio.get_event_loop().run_until_complete(
            _collect_events(agent, "read a file")
        )

        # read_file should NOT trigger confirmation (it's not destructive)
        assert "read_file" not in confirm_calls
        # But the tool should still execute
        read_mock.assert_called_once()

    def test_deny_sends_denial_to_llm(self):
        """When a tool is denied, the denial message is added to messages so LLM can adapt."""
        mock_provider = MagicMock(spec=GLMProvider)
        tc1 = _make_tool_call_delta(0, id="tc1", name="bash", arguments='{"command": "rm -rf /"}')
        mock_provider.chat.side_effect = [
            iter([_make_chunk(tool_calls=[tc1], finish_reason="tool_calls")]),
            iter([_make_chunk(content="Understood, I won't do that.", finish_reason="stop")]),
        ]

        bash_mock = MagicMock(return_value="should not run")
        tools = {"bash": bash_mock}
        agent = Agent(
            provider=mock_provider,
            tools=tools,
            tool_schemas=[],
            confirm_fn=lambda name, args: False,
        )

        asyncio.get_event_loop().run_until_complete(
            _collect_events(agent, "delete everything")
        )

        # Check that a tool message with "denied" was added to conversation
        tool_msgs = [m for m in agent.state.messages if m.get("role") == "tool"]
        assert len(tool_msgs) == 1
        assert "denied" in tool_msgs[0]["content"].lower()

    def test_confirm_fn_called_for_write_file(self):
        """write_file is a destructive tool and triggers confirmation."""
        mock_provider = MagicMock(spec=GLMProvider)
        tc1 = _make_tool_call_delta(0, id="tc1", name="write_file", arguments='{"path": "/tmp/test", "content": "hi"}')
        mock_provider.chat.side_effect = [
            iter([_make_chunk(tool_calls=[tc1], finish_reason="tool_calls")]),
            iter([_make_chunk(content="Written!", finish_reason="stop")]),
        ]

        write_mock = MagicMock(return_value="[OK] Wrote 1 lines to /tmp/test")
        tools = {"write_file": write_mock}

        confirm_calls = []
        def track_confirm(name, args):
            confirm_calls.append(name)
            return True

        agent = Agent(
            provider=mock_provider,
            tools=tools,
            tool_schemas=[],
            confirm_fn=track_confirm,
        )

        asyncio.get_event_loop().run_until_complete(
            _collect_events(agent, "write a file")
        )

        assert "write_file" in confirm_calls
        write_mock.assert_called_once()

    def test_confirm_fn_called_for_edit_file(self):
        """edit_file is a destructive tool and triggers confirmation."""
        mock_provider = MagicMock(spec=GLMProvider)
        tc1 = _make_tool_call_delta(0, id="tc1", name="edit_file", arguments='{"path": "test.py", "old_string": "x", "new_string": "y"}')
        mock_provider.chat.side_effect = [
            iter([_make_chunk(tool_calls=[tc1], finish_reason="tool_calls")]),
            iter([_make_chunk(content="Edited!", finish_reason="stop")]),
        ]

        edit_mock = MagicMock(return_value="[OK] Replaced 1 occurrence in test.py")
        tools = {"edit_file": edit_mock}

        confirm_calls = []
        def track_confirm(name, args):
            confirm_calls.append(name)
            return True

        agent = Agent(
            provider=mock_provider,
            tools=tools,
            tool_schemas=[],
            confirm_fn=track_confirm,
        )

        asyncio.get_event_loop().run_until_complete(
            _collect_events(agent, "edit a file")
        )

        assert "edit_file" in confirm_calls
        edit_mock.assert_called_once()

    def test_destructive_tools_constant(self):
        """DESTRUCTIVE_TOOLS contains exactly bash, write_file, edit_file, copy_file, rename, mkdir."""
        assert Agent.DESTRUCTIVE_TOOLS == {"bash", "write_file", "edit_file", "copy_file", "rename", "mkdir"}
