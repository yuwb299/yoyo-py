"""Tests for parallel tool execution.

When the LLM returns multiple tool calls, read-only tools (read_file, search,
list_files, glob) are executed concurrently using asyncio. Destructive tools
(bash, write_file, edit_file, rename) always execute sequentially.
"""

import asyncio
import json
import time
from unittest.mock import MagicMock

import pytest

from src.agent import Agent, AgentEvent
from src.provider import GLMProvider, Usage


# ── Helpers ─────────────────────────────────────────────────────────────

def _make_provider():
    """Create a mock GLMProvider that doesn't need a real API key."""
    provider = MagicMock(spec=GLMProvider)
    provider.model = "test-model"
    provider.parse_usage = GLMProvider.parse_usage
    return provider


def _slow_tool(name, delay=0.1):
    """Create a tool that takes 'delay' seconds — used to verify parallelism."""
    def tool_fn(**kwargs):
        time.sleep(delay)
        return f"{name}-done"
    return tool_fn


def _make_tool_call_delta(index, id=None, name=None, arguments=None):
    """Create a mock tool call delta with real string attributes."""
    tc = MagicMock()
    tc.index = index
    tc.id = id
    tc.function = MagicMock()
    tc.function.name = name
    tc.function.arguments = arguments
    return tc


def _make_stream_chunks(tool_calls, finish_reason="tool_calls"):
    """Build mock stream chunks that simulate multi-tool-call LLM response."""
    chunks = []

    for i, tc in enumerate(tool_calls):
        # id + name chunk
        delta_tc = _make_tool_call_delta(
            index=i,
            id=tc["id"],
            name=tc["function"]["name"],
            arguments="",
        )
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta = MagicMock(content=None, tool_calls=[delta_tc])
        chunk.choices[0].finish_reason = None
        chunk.usage = None
        chunks.append(chunk)

        # arguments chunk
        delta_tc2 = _make_tool_call_delta(
            index=i,
            id=None,
            name=None,
            arguments=tc["function"]["arguments"],
        )
        chunk2 = MagicMock()
        chunk2.choices = [MagicMock()]
        chunk2.choices[0].delta = MagicMock(content=None, tool_calls=[delta_tc2])
        chunk2.choices[0].finish_reason = None
        chunk2.usage = None
        chunks.append(chunk2)

    # Final chunk with finish_reason and usage
    final = MagicMock()
    final.choices = [MagicMock()]
    final.choices[0].delta = MagicMock(content=None, tool_calls=None)
    final.choices[0].finish_reason = finish_reason
    final.usage = MagicMock()
    final.usage.prompt_tokens = 100
    final.usage.completion_tokens = 50
    chunks.append(final)

    return chunks


async def _collect_events(agent, prompt):
    """Collect all events from agent.prompt()."""
    events = []
    async for event in agent.prompt(prompt):
        events.append(event)
    return events


def _run_agent_prompt(agent, prompt):
    """Synchronous wrapper for agent.prompt()."""
    return asyncio.get_event_loop().run_until_complete(_collect_events(agent, prompt))


# ── Tests ───────────────────────────────────────────────────────────────


class TestParallelReadOnlyTools:
    """Read-only tools should execute concurrently."""

    def test_two_read_files_execute_concurrently(self):
        """Two read_file calls should run in parallel (total time < sequential)."""
        call_times = []

        def slow_read(**kwargs):
            call_times.append(time.monotonic())
            time.sleep(0.15)  # Simulate slow file read
            return f"content of {kwargs.get('path', '?')}"

        provider = _make_provider()
        tools = {"read_file": slow_read}
        schemas = [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                        },
                        "required": ["path"],
                    },
                },
            }
        ]

        agent = Agent(
            provider=provider,
            system_prompt="test",
            tools=tools,
            tool_schemas=schemas,
        )

        tool_calls_data = [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "read_file",
                    "arguments": json.dumps({"path": "a.py"}),
                },
            },
            {
                "id": "call_2",
                "type": "function",
                "function": {
                    "name": "read_file",
                    "arguments": json.dumps({"path": "b.py"}),
                },
            },
        ]

        chunks = _make_stream_chunks(tool_calls_data)
        provider.chat.return_value = iter(chunks)

        events = _run_agent_prompt(agent, "read both files")

        # Both tools should have been executed
        tool_end_events = [
            (t, d) for t, d in events if t == AgentEvent.TOOL_END
        ]
        assert len(tool_end_events) == 2

        # Verify both calls happened roughly at the same time (parallel)
        # If sequential, difference would be ~0.15s; parallel should be < 0.1s
        if len(call_times) >= 2:
            gap = abs(call_times[1] - call_times[0])
            assert gap < 0.10, f"Tools ran sequentially (gap={gap:.3f}s), expected parallel"

    def test_read_and_search_execute_concurrently(self):
        """read_file and search (both read-only) should run in parallel."""
        call_times = []

        def slow_read(**kwargs):
            call_times.append(("read", time.monotonic()))
            time.sleep(0.15)
            return "file content"

        def slow_search(**kwargs):
            call_times.append(("search", time.monotonic()))
            time.sleep(0.15)
            return "search results"

        provider = _make_provider()
        tools = {"read_file": slow_read, "search": slow_search}
        schemas = [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "parameters": {
                        "type": "object",
                        "properties": {"pattern": {"type": "string"}},
                        "required": ["pattern"],
                    },
                },
            },
        ]

        agent = Agent(
            provider=provider,
            system_prompt="test",
            tools=tools,
            tool_schemas=schemas,
        )

        tool_calls_data = [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "read_file",
                    "arguments": json.dumps({"path": "test.py"}),
                },
            },
            {
                "id": "call_2",
                "type": "function",
                "function": {
                    "name": "search",
                    "arguments": json.dumps({"pattern": "TODO"}),
                },
            },
        ]

        chunks = _make_stream_chunks(tool_calls_data)
        provider.chat.return_value = iter(chunks)

        events = _run_agent_prompt(agent, "read file and search")

        tool_end_events = [
            (t, d) for t, d in events if t == AgentEvent.TOOL_END
        ]
        assert len(tool_end_events) == 2

        if len(call_times) >= 2:
            gap = abs(call_times[1][1] - call_times[0][1])
            assert gap < 0.10, f"Tools ran sequentially (gap={gap:.3f}s), expected parallel"

    def test_glob_and_list_files_concurrently(self):
        """glob and list_files (both read-only) should run in parallel."""
        call_times = []

        def slow_glob(**kwargs):
            call_times.append(("glob", time.monotonic()))
            time.sleep(0.15)
            return "file1.py\nfile2.py"

        def slow_list(**kwargs):
            call_times.append(("list", time.monotonic()))
            time.sleep(0.15)
            return "dir contents"

        provider = _make_provider()
        tools = {"glob": slow_glob, "list_files": slow_list}
        schemas = [
            {
                "type": "function",
                "function": {
                    "name": "glob",
                    "parameters": {
                        "type": "object",
                        "properties": {"pattern": {"type": "string"}},
                        "required": ["pattern"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_files",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": [],
                    },
                },
            },
        ]

        agent = Agent(
            provider=provider,
            system_prompt="test",
            tools=tools,
            tool_schemas=schemas,
        )

        tool_calls_data = [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "glob",
                    "arguments": json.dumps({"pattern": "**/*.py"}),
                },
            },
            {
                "id": "call_2",
                "type": "function",
                "function": {
                    "name": "list_files",
                    "arguments": json.dumps({"path": "."}),
                },
            },
        ]

        chunks = _make_stream_chunks(tool_calls_data)
        provider.chat.return_value = iter(chunks)

        events = _run_agent_prompt(agent, "glob and list")

        tool_end_events = [
            (t, d) for t, d in events if t == AgentEvent.TOOL_END
        ]
        assert len(tool_end_events) == 2

        if len(call_times) >= 2:
            gap = abs(call_times[1][1] - call_times[0][1])
            assert gap < 0.10, f"Tools ran sequentially (gap={gap:.3f}s), expected parallel"


class TestSequentialDestructiveTools:
    """Destructive tools (bash, write_file, edit_file, rename) should stay sequential."""

    def test_two_bash_tools_run_sequentially(self):
        """Two bash calls should run sequentially (not in parallel)."""
        call_times = []

        def slow_bash(**kwargs):
            call_times.append(time.monotonic())
            time.sleep(0.15)
            return "done"

        provider = _make_provider()
        tools = {"bash": slow_bash}
        schemas = [
            {
                "type": "function",
                "function": {
                    "name": "bash",
                    "parameters": {
                        "type": "object",
                        "properties": {"command": {"type": "string"}},
                        "required": ["command"],
                    },
                },
            }
        ]

        agent = Agent(
            provider=provider,
            system_prompt="test",
            tools=tools,
            tool_schemas=schemas,
            confirm_fn=lambda name, args: True,  # Auto-approve
        )

        tool_calls_data = [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "bash",
                    "arguments": json.dumps({"command": "echo a"}),
                },
            },
            {
                "id": "call_2",
                "type": "function",
                "function": {
                    "name": "bash",
                    "arguments": json.dumps({"command": "echo b"}),
                },
            },
        ]

        chunks = _make_stream_chunks(tool_calls_data)
        provider.chat.return_value = iter(chunks)

        events = _run_agent_prompt(agent, "run two commands")

        tool_end_events = [
            (t, d) for t, d in events if t == AgentEvent.TOOL_END
        ]
        assert len(tool_end_events) == 2

        # Bash calls should be sequential — gap should be >= 0.10s
        if len(call_times) >= 2:
            gap = abs(call_times[1] - call_times[0])
            assert gap >= 0.10, f"Bash tools ran in parallel (gap={gap:.3f}s), expected sequential"

    def test_mixed_tools_destructive_forces_sequential(self):
        """If any tool is destructive, all tools in the batch run sequentially."""
        call_times = []

        def slow_read(**kwargs):
            call_times.append(("read", time.monotonic()))
            time.sleep(0.15)
            return "content"

        def slow_bash(**kwargs):
            call_times.append(("bash", time.monotonic()))
            time.sleep(0.15)
            return "done"

        provider = _make_provider()
        tools = {"read_file": slow_read, "bash": slow_bash}
        schemas = [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "bash",
                    "parameters": {
                        "type": "object",
                        "properties": {"command": {"type": "string"}},
                        "required": ["command"],
                    },
                },
            },
        ]

        agent = Agent(
            provider=provider,
            system_prompt="test",
            tools=tools,
            tool_schemas=schemas,
            confirm_fn=lambda name, args: True,
        )

        # read_file first, then bash — mixed
        tool_calls_data = [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "read_file",
                    "arguments": json.dumps({"path": "test.py"}),
                },
            },
            {
                "id": "call_2",
                "type": "function",
                "function": {
                    "name": "bash",
                    "arguments": json.dumps({"command": "echo hi"}),
                },
            },
        ]

        chunks = _make_stream_chunks(tool_calls_data)
        provider.chat.return_value = iter(chunks)

        events = _run_agent_prompt(agent, "read and run")

        assert len([(t, d) for t, d in events if t == AgentEvent.TOOL_END]) == 2

        # Since there's a destructive tool, everything should be sequential
        if len(call_times) >= 2:
            gap = abs(call_times[1][1] - call_times[0][1])
            assert gap >= 0.10, (
                f"Mixed tools ran in parallel (gap={gap:.3f}s), expected sequential"
            )

    def test_two_write_tools_sequential(self):
        """Two write_file calls should run sequentially."""
        call_times = []

        def slow_write(**kwargs):
            call_times.append(time.monotonic())
            time.sleep(0.15)
            return "wrote"

        provider = _make_provider()
        tools = {"write_file": slow_write}
        schemas = [
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["path", "content"],
                    },
                },
            }
        ]

        agent = Agent(
            provider=provider,
            system_prompt="test",
            tools=tools,
            tool_schemas=schemas,
            confirm_fn=lambda name, args: True,
        )

        tool_calls_data = [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "write_file",
                    "arguments": json.dumps({"path": "a.py", "content": "hello"}),
                },
            },
            {
                "id": "call_2",
                "type": "function",
                "function": {
                    "name": "write_file",
                    "arguments": json.dumps({"path": "b.py", "content": "world"}),
                },
            },
        ]

        chunks = _make_stream_chunks(tool_calls_data)
        provider.chat.return_value = iter(chunks)

        events = _run_agent_prompt(agent, "write two files")

        tool_end_events = [
            (t, d) for t, d in events if t == AgentEvent.TOOL_END
        ]
        assert len(tool_end_events) == 2

        if len(call_times) >= 2:
            gap = abs(call_times[1] - call_times[0])
            assert gap >= 0.10, f"Write tools ran in parallel (gap={gap:.3f}s), expected sequential"


class TestToolResultsOrdering:
    """Tool results must maintain correct tool_call_id ordering regardless of
    execution order — the API requires results in the same order as tool_calls."""

    def test_parallel_results_preserve_order(self):
        """Even if tool B finishes before tool A, results are appended in order."""
        def fast_read(**kwargs):
            path = kwargs.get("path", "?")
            # First call is slow, second is fast — if parallel, second finishes first
            if path == "slow.py":
                time.sleep(0.2)
            return f"content of {path}"

        provider = _make_provider()
        tools = {"read_file": fast_read}
        schemas = [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            }
        ]

        agent = Agent(
            provider=provider,
            system_prompt="test",
            tools=tools,
            tool_schemas=schemas,
        )

        tool_calls_data = [
            {
                "id": "call_slow",
                "type": "function",
                "function": {
                    "name": "read_file",
                    "arguments": json.dumps({"path": "slow.py"}),
                },
            },
            {
                "id": "call_fast",
                "type": "function",
                "function": {
                    "name": "read_file",
                    "arguments": json.dumps({"path": "fast.py"}),
                },
            },
        ]

        chunks = _make_stream_chunks(tool_calls_data)
        provider.chat.return_value = iter(chunks)

        events = _run_agent_prompt(agent, "read both")

        # Check messages in conversation: tool results should be in the original order
        tool_msgs = [
            m for m in agent.state.messages if m.get("role") == "tool"
        ]
        assert len(tool_msgs) == 2
        # First tool message should be for call_slow, second for call_fast
        assert tool_msgs[0]["tool_call_id"] == "call_slow"
        assert tool_msgs[1]["tool_call_id"] == "call_fast"
        # Content should match
        assert "slow.py" in tool_msgs[0]["content"]
        assert "fast.py" in tool_msgs[1]["content"]

    def test_three_parallel_results_preserve_order(self):
        """Three parallel tools should preserve call order in results."""
        order = []

        def tracked_read(**kwargs):
            order.append(kwargs.get("path", "?"))
            time.sleep(0.1)
            return f"content of {kwargs.get('path', '?')}"

        provider = _make_provider()
        tools = {"read_file": tracked_read}
        schemas = [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            }
        ]

        agent = Agent(
            provider=provider,
            system_prompt="test",
            tools=tools,
            tool_schemas=schemas,
        )

        tool_calls_data = [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "read_file",
                    "arguments": json.dumps({"path": "first.py"}),
                },
            },
            {
                "id": "call_2",
                "type": "function",
                "function": {
                    "name": "read_file",
                    "arguments": json.dumps({"path": "second.py"}),
                },
            },
            {
                "id": "call_3",
                "type": "function",
                "function": {
                    "name": "read_file",
                    "arguments": json.dumps({"path": "third.py"}),
                },
            },
        ]

        chunks = _make_stream_chunks(tool_calls_data)
        provider.chat.return_value = iter(chunks)

        events = _run_agent_prompt(agent, "read three files")

        tool_msgs = [
            m for m in agent.state.messages if m.get("role") == "tool"
        ]
        assert len(tool_msgs) == 3
        assert tool_msgs[0]["tool_call_id"] == "call_1"
        assert tool_msgs[1]["tool_call_id"] == "call_2"
        assert tool_msgs[2]["tool_call_id"] == "call_3"


class TestParallelInterrupt:
    """Interrupt handling should work correctly with parallel execution."""

    def test_interrupt_still_works_with_parallel(self):
        """Setting _interrupted should produce INTERRUPTED event even with parallel tools."""
        executed = []

        def tool_a(**kwargs):
            executed.append("a")
            time.sleep(0.1)
            return "a result"

        def tool_b(**kwargs):
            executed.append("b")
            time.sleep(0.1)
            return "b result"

        provider = _make_provider()
        tools = {"read_file": tool_a, "search": tool_b}
        schemas = [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "parameters": {
                        "type": "object",
                        "properties": {"pattern": {"type": "string"}},
                        "required": ["pattern"],
                    },
                },
            },
        ]

        agent = Agent(
            provider=provider,
            system_prompt="test",
            tools=tools,
            tool_schemas=schemas,
        )

        tool_calls_data = [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "read_file",
                    "arguments": json.dumps({"path": "a.py"}),
                },
            },
            {
                "id": "call_2",
                "type": "function",
                "function": {
                    "name": "search",
                    "arguments": json.dumps({"pattern": "test"}),
                },
            },
        ]

        chunks = _make_stream_chunks(tool_calls_data)
        provider.chat.return_value = iter(chunks)

        # Interrupt immediately after first event
        events = []
        async def _collect():
            nonlocal events
            async for event in agent.prompt("read and search"):
                events.append(event)
                if len(events) == 1:
                    agent.interrupt()

        asyncio.get_event_loop().run_until_complete(_collect())

        # Should have INTERRUPTED event
        event_types = [e[0] for e in events]
        assert AgentEvent.INTERRUPTED in event_types


class TestSingleToolBackwardsCompat:
    """Single tool calls should work exactly as before."""

    def test_single_read_file_unchanged(self):
        """A single tool call should produce the same events as before."""
        def read_fn(**kwargs):
            return f"content of {kwargs.get('path', '?')}"

        provider = _make_provider()
        tools = {"read_file": read_fn}
        schemas = [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            }
        ]

        agent = Agent(
            provider=provider,
            system_prompt="test",
            tools=tools,
            tool_schemas=schemas,
        )

        tool_calls_data = [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "read_file",
                    "arguments": json.dumps({"path": "test.py"}),
                },
            },
        ]

        chunks = _make_stream_chunks(tool_calls_data)
        provider.chat.return_value = iter(chunks)

        events = _run_agent_prompt(agent, "read test.py")

        # Should have: TOOL_START, TOOL_END for the tool, then DONE
        event_types = [e[0] for e in events]
        assert AgentEvent.TOOL_START in event_types
        assert AgentEvent.TOOL_END in event_types

        # Check tool result in messages
        tool_msgs = [m for m in agent.state.messages if m.get("role") == "tool"]
        assert len(tool_msgs) == 1
        assert "test.py" in tool_msgs[0]["content"]

    def test_unknown_tool_still_errors(self):
        """Unknown tools should still produce an error result."""
        provider = _make_provider()
        agent = Agent(
            provider=provider,
            system_prompt="test",
            tools={},
            tool_schemas=[],
        )

        tool_calls_data = [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "nonexistent",
                    "arguments": json.dumps({}),
                },
            },
        ]

        chunks = _make_stream_chunks(tool_calls_data)
        provider.chat.return_value = iter(chunks)

        events = _run_agent_prompt(agent, "use unknown tool")

        tool_end_events = [
            (t, d) for t, d in events if t == AgentEvent.TOOL_END
        ]
        assert len(tool_end_events) == 1
        assert tool_end_events[0][1]["is_error"] is True
        assert "Unknown tool" in tool_end_events[0][1]["output"]

    def test_malformed_json_still_errors(self):
        """Malformed JSON in tool args should still produce an error result."""
        def read_fn(**kwargs):
            return "should not be called"

        provider = _make_provider()
        tools = {"read_file": read_fn}
        schemas = [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            }
        ]

        agent = Agent(
            provider=provider,
            system_prompt="test",
            tools=tools,
            tool_schemas=schemas,
        )

        tool_calls_data = [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "read_file",
                    "arguments": "{bad json!!!",
                },
            },
        ]

        chunks = _make_stream_chunks(tool_calls_data)
        provider.chat.return_value = iter(chunks)

        events = _run_agent_prompt(agent, "read file")

        tool_end_events = [
            (t, d) for t, d in events if t == AgentEvent.TOOL_END
        ]
        assert len(tool_end_events) == 1
        assert tool_end_events[0][1]["is_error"] is True
        assert "Malformed JSON" in tool_end_events[0][1]["output"]

    def test_permission_denied_still_works(self):
        """Permission denied should work as before with parallel execution."""
        call_count = 0

        def bash_fn(**kwargs):
            nonlocal call_count
            call_count += 1
            return "should not be called"

        provider = _make_provider()
        tools = {"bash": bash_fn}
        schemas = [
            {
                "type": "function",
                "function": {
                    "name": "bash",
                    "parameters": {
                        "type": "object",
                        "properties": {"command": {"type": "string"}},
                        "required": ["command"],
                    },
                },
            }
        ]

        agent = Agent(
            provider=provider,
            system_prompt="test",
            tools=tools,
            tool_schemas=schemas,
            confirm_fn=lambda name, args: False,  # Deny all
        )

        tool_calls_data = [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "bash",
                    "arguments": json.dumps({"command": "rm -rf /"}),
                },
            },
        ]

        chunks = _make_stream_chunks(tool_calls_data)
        provider.chat.return_value = iter(chunks)

        events = _run_agent_prompt(agent, "delete everything")

        tool_end_events = [
            (t, d) for t, d in events if t == AgentEvent.TOOL_END
        ]
        assert len(tool_end_events) == 1
        assert tool_end_events[0][1]["is_error"] is True
        assert "Permission denied" in tool_end_events[0][1]["output"]
        assert call_count == 0  # Tool should never have been called
