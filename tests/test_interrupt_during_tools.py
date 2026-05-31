"""Tests for interrupt handling during tool execution.

Bug: When the agent is interrupted (Ctrl+C) during tool execution, the
conversation has an assistant message with tool_calls but not all tool
responses. The next API call will fail because tool_call_ids are unmatched.

Fix: Append placeholder error messages for unanswered tool_calls on interrupt.
"""

import asyncio
import json
import pytest
from unittest.mock import MagicMock, patch

from src.agent import Agent, AgentEvent, AgentState
from src.provider import Usage


def _make_chunk(content=None, tool_calls=None, finish_reason=None, usage=None):
    """Create a mock stream chunk."""
    chunk = MagicMock()
    chunk.choices = [MagicMock()]
    chunk.choices[0].delta = MagicMock()
    chunk.choices[0].delta.content = content
    chunk.choices[0].delta.tool_calls = tool_calls
    chunk.choices[0].finish_reason = finish_reason
    chunk.usage = usage
    return chunk


def _make_tc_chunk(index, tc_id="", name="", arguments="", finish_reason=None):
    """Create a tool call delta chunk."""
    chunk = MagicMock()
    chunk.choices = [MagicMock()]
    chunk.choices[0].delta = MagicMock()
    chunk.choices[0].delta.content = None
    tc = MagicMock()
    tc.index = index
    tc.id = tc_id
    tc.function = MagicMock()
    tc.function.name = name
    tc.function.arguments = arguments
    chunk.choices[0].delta.tool_calls = [tc]
    chunk.choices[0].finish_reason = finish_reason
    chunk.usage = None
    return chunk


def _collect_events(agent, user_input):
    """Collect all events from an agent prompt."""
    loop = asyncio.new_event_loop()
    events = []

    async def _run():
        async for event in agent.prompt(user_input):
            events.append(event)

    loop.run_until_complete(_run())
    loop.close()
    return events


class TestInterruptDuringToolExecution:
    """Test that interrupt during tool execution leaves valid conversation state."""

    def test_interrupt_between_tool_calls_appends_remaining_errors(self):
        """When interrupted after first tool but before second, remaining tools get error responses."""
        # First response: LLM requests 2 tool calls
        tc1_chunk = _make_tc_chunk(0, tc_id="call_1", name="read_file", arguments='{"path": "a.py"}')
        tc1_done = _make_tc_chunk(0, finish_reason="tool_calls")
        tc2_chunk = _make_tc_chunk(1, tc_id="call_2", name="bash", arguments='{"command": "ls"}')
        tc2_done = _make_tc_chunk(1, finish_reason="tool_calls")
        finish_chunk = _make_chunk(finish_reason="tool_calls")

        first_response = [tc1_chunk, tc1_done, tc2_chunk, tc2_done, finish_chunk]

        mock_provider = MagicMock()
        mock_provider.chat.return_value = iter(first_response)

        # Tool implementations
        def mock_read_file(**kwargs):
            return "[File: a.py (10 lines)]"

        tools = {
            "read_file": mock_read_file,
            "bash": lambda **kw: "file1\nfile2",
        }
        tool_schemas = [
            {"type": "function", "function": {"name": "read_file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
            {"type": "function", "function": {"name": "bash", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
        ]

        agent = Agent(
            provider=mock_provider,
            system_prompt="test",
            tools=tools,
            tool_schemas=tool_schemas,
        )

        # Interrupt after the first tool executes
        call_count = [0]
        original_interrupt = agent.interrupt

        def interrupt_after_first():
            # Let first tool execute normally, then set interrupt before second
            agent._interrupted = True

        # We'll manually trigger interrupt during tool execution
        # The trick: the for loop in prompt() checks self._interrupted at the start
        # of each tool call iteration. So we set it after the first tool.

        # Actually, let's use a different approach: interrupt the agent
        # right after the first tool call runs. We do this by patching
        # the tool to set the interrupt flag.

        def mock_read_file_interrupt(**kwargs):
            result = "[File: a.py (10 lines)]"
            # After this tool runs, the next iteration will see _interrupted=True
            agent._interrupted = True
            return result

        tools["read_file"] = mock_read_file_interrupt

        events = _collect_events(agent, "test interrupt")

        # Should get INTERRUPTED event
        event_types = [e[0] for e in events]
        assert AgentEvent.INTERRUPTED in event_types

        # Check messages: should have error tool responses for all unanswered tools
        messages = agent.state.messages

        # Find tool messages
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        # First tool should have succeeded
        assert len(tool_msgs) >= 1
        assert tool_msgs[0]["tool_call_id"] == "call_1"
        assert "[File: a.py" in tool_msgs[0]["content"]

        # Second tool should have an error response (interrupt placeholder)
        assert len(tool_msgs) == 2, f"Expected 2 tool messages, got {len(tool_msgs)}: {tool_msgs}"
        assert tool_msgs[1]["tool_call_id"] == "call_2"
        assert "interrupted" in tool_msgs[1]["content"].lower()

    def test_interrupt_after_all_tools_no_extra_messages(self):
        """When all tools execute before interrupt, no extra error messages needed."""
        tc_chunk = _make_tc_chunk(0, tc_id="call_1", name="read_file", arguments='{"path": "x.py"}')
        finish = _make_chunk(finish_reason="tool_calls")

        first_response = [tc_chunk, finish]
        # Second response: text only (tool results processed, LLM responds with text)
        text_chunk = _make_chunk(content="Done!")
        text_done = _make_chunk(finish_reason="stop")
        second_response = [text_chunk, text_done]

        mock_provider = MagicMock()
        # First call returns tool call, second returns text
        mock_provider.chat.side_effect = [iter(first_response), iter(second_response)]

        tools = {"read_file": lambda **kw: "[File: x.py (5 lines)]"}
        tool_schemas = [
            {"type": "function", "function": {"name": "read_file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
        ]

        agent = Agent(
            provider=mock_provider,
            system_prompt="test",
            tools=tools,
            tool_schemas=tool_schemas,
        )

        events = _collect_events(agent, "read x.py")

        # Should complete normally
        event_types = [e[0] for e in events]
        assert AgentEvent.DONE in event_types

        # No interrupt-related error messages
        tool_msgs = [m for m in agent.state.messages if m.get("role") == "tool"]
        assert len(tool_msgs) == 1
        assert "interrupted" not in tool_msgs[0]["content"].lower()

    def test_interrupt_before_first_tool_still_has_assistant_msg(self):
        """When interrupted via flag inside tool func before any tool executes, placeholders added."""
        tc1 = _make_tc_chunk(0, tc_id="call_1", name="bash", arguments='{"command": "ls"}')
        tc2 = _make_tc_chunk(1, tc_id="call_2", name="bash", arguments='{"command": "pwd"}')
        finish = _make_chunk(finish_reason="tool_calls")

        mock_provider = MagicMock()
        mock_provider.chat.return_value = iter([tc1, tc2, finish])

        # First tool call sets interrupt, returns output; second never executes
        def bash_interrupt(**kw):
            agent._interrupted = True
            return "output"

        tools = {"bash": bash_interrupt}
        tool_schemas = [
            {"type": "function", "function": {"name": "bash", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
        ]

        agent = Agent(
            provider=mock_provider,
            system_prompt="test",
            tools=tools,
            tool_schemas=tool_schemas,
        )

        events = _collect_events(agent, "run stuff")

        event_types = [e[0] for e in events]
        assert AgentEvent.INTERRUPTED in event_types

        # Both tool calls should have messages: first has output, second has error placeholder
        tool_msgs = [m for m in agent.state.messages if m.get("role") == "tool"]
        assert len(tool_msgs) == 2, f"Expected 2 tool messages, got {len(tool_msgs)}"
        assert tool_msgs[0]["tool_call_id"] == "call_1"
        assert "interrupted" in tool_msgs[1]["content"].lower()

    def test_interrupt_leaves_valid_conversation_structure(self):
        """After interrupt during tools, the conversation structure should be valid."""
        tc1 = _make_tc_chunk(0, tc_id="call_1", name="read_file", arguments='{"path": "a.py"}')
        tc2 = _make_tc_chunk(1, tc_id="call_2", name="bash", arguments='{"command": "ls"}')
        finish = _make_chunk(finish_reason="tool_calls")

        mock_provider = MagicMock()
        mock_provider.chat.return_value = iter([tc1, tc2, finish])

        def read_and_interrupt(**kwargs):
            agent._interrupted = True
            return "file contents"

        tools = {"read_file": read_and_interrupt, "bash": lambda **kw: "output"}
        tool_schemas = [
            {"type": "function", "function": {"name": "read_file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
            {"type": "function", "function": {"name": "bash", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
        ]

        agent = Agent(
            provider=mock_provider,
            system_prompt="test",
            tools=tools,
            tool_schemas=tool_schemas,
        )

        events = _collect_events(agent, "test")

        # Validate conversation structure
        issues = Agent._validate_messages(agent.state.messages)
        assert issues == [], f"Conversation has structural issues: {issues}"

    def test_all_tool_call_ids_have_matching_responses(self):
        """Every tool_call_id in assistant messages must have a tool response."""
        tc1 = _make_tc_chunk(0, tc_id="call_1", name="read_file", arguments='{"path": "a.py"}')
        tc2 = _make_tc_chunk(1, tc_id="call_2", name="bash", arguments='{"command": "ls"}')
        tc3 = _make_tc_chunk(2, tc_id="call_3", name="bash", arguments='{"command": "pwd"}')
        finish = _make_chunk(finish_reason="tool_calls")

        mock_provider = MagicMock()
        mock_provider.chat.return_value = iter([tc1, tc2, tc3, finish])

        call_count = [0]

        def interrupt_on_second(**kwargs):
            call_count[0] += 1
            if call_count[0] >= 2:
                agent._interrupted = True
            return "output"

        tools = {"read_file": interrupt_on_second, "bash": interrupt_on_second}
        tool_schemas = [
            {"type": "function", "function": {"name": "read_file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
            {"type": "function", "function": {"name": "bash", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
        ]

        agent = Agent(
            provider=mock_provider,
            system_prompt="test",
            tools=tools,
            tool_schemas=tool_schemas,
        )

        events = _collect_events(agent, "test")

        # Collect all tool_call_ids from assistant messages
        all_tool_call_ids = set()
        for m in agent.state.messages:
            if m.get("role") == "assistant" and m.get("tool_calls"):
                for tc in m["tool_calls"]:
                    all_tool_call_ids.add(tc.get("id"))

        # Collect all tool_call_ids from tool responses
        tool_response_ids = set()
        for m in agent.state.messages:
            if m.get("role") == "tool":
                tool_response_ids.add(m.get("tool_call_id"))

        # Every tool_call_id must have a response
        assert all_tool_call_ids == tool_response_ids, (
            f"Unmatched tool_call_ids: {all_tool_call_ids - tool_response_ids}"
        )
