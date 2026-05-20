"""Agent core — the main loop that drives conversation with tool calling."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from .provider import GLMProvider, Usage


class AgentEvent(Enum):
    """Events emitted by the agent during execution."""
    TEXT = "text"              # Streaming text delta
    TOOL_START = "tool_start"  # Tool execution started
    TOOL_END = "tool_end"      # Tool execution finished
    DONE = "done"              # Agent turn complete
    ERROR = "error"            # Error occurred


@dataclass
class ToolResult:
    """Result from a tool execution."""
    tool_call_id: str
    name: str
    output: str
    is_error: bool = False


@dataclass
class AgentState:
    """Mutable agent state."""
    messages: list[dict[str, Any]] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    max_tool_rounds: int = 20  # Safety: max tool-calling rounds per prompt


class Agent:
    """Self-evolving coding agent with tool-calling loop.

    The agent loop:
    1. Send messages to LLM
    2. If LLM returns tool_calls, execute them and append results
    3. Send updated messages back to LLM
    4. Repeat until LLM returns text only (no more tool calls)
    5. Emit streaming text and tool events to caller
    """

    def __init__(
        self,
        provider: GLMProvider,
        system_prompt: str = "",
        tools: dict[str, Callable] | None = None,
        tool_schemas: list[dict] | None = None,
        max_tool_rounds: int = 20,
        verbose: bool = False,
    ):
        self.provider = provider
        self.system_prompt = system_prompt
        self.tools = tools or {}
        self.tool_schemas = tool_schemas or []
        self.state = AgentState(max_tool_rounds=max_tool_rounds)
        self.verbose = verbose

        if self.system_prompt:
            self.state.messages = [
                {"role": "system", "content": self.system_prompt}
            ]

    def clear(self) -> None:
        """Reset conversation history."""
        self.state.messages = (
            [{"role": "system", "content": self.system_prompt}]
            if self.system_prompt
            else []
        )
        self.state.usage = Usage()

    def register_tool(self, name: str, func: Callable, schema: dict) -> None:
        """Register a tool function and its OpenAI-format schema."""
        self.tools[name] = func
        self.tool_schemas.append(schema)

    async def prompt(self, user_input: str) -> None:
        """Run one user prompt through the agent loop.

        Yields (AgentEvent, data) tuples:
        - (TEXT, str_delta) — streaming text from the LLM
        - (TOOL_START, {name, args}) — tool about to execute
        - (TOOL_END, {name, output, is_error}) — tool finished
        - (DONE, Usage) — agent turn complete
        - (ERROR, str) — error message
        """
        self.state.messages.append({"role": "user", "content": user_input})

        for round_num in range(self.state.max_tool_rounds):
            try:
                response = self.provider.chat(
                    messages=self.state.messages,
                    tools=self.tool_schemas if self.tool_schemas else None,
                    stream=True,
                )
            except Exception as e:
                yield (AgentEvent.ERROR, str(e))
                return

            # Collect the full assistant message from the stream
            assistant_content = ""
            tool_calls_list: list[dict] = []
            current_tool_calls: dict[int, dict] = {}
            round_usage = Usage()

            try:
                for chunk in response:
                    # Accumulate usage from chunks
                    if hasattr(chunk, "usage") and chunk.usage:
                        round_usage.add(GLMProvider.parse_usage(chunk))

                    if not chunk.choices:
                        continue

                    delta = chunk.choices[0].delta

                    # Handle text content
                    if delta.content:
                        assistant_content += delta.content
                        yield (AgentEvent.TEXT, delta.content)

                    # Handle tool calls (streaming accumulation)
                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index
                            if idx not in current_tool_calls:
                                current_tool_calls[idx] = {
                                    "id": tc.id or "",
                                    "type": "function",
                                    "function": {
                                        "name": "",
                                        "arguments": "",
                                    },
                                }
                            if tc.id:
                                current_tool_calls[idx]["id"] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    current_tool_calls[idx]["function"]["name"] += (
                                        tc.function.name
                                    )
                                if tc.function.arguments:
                                    current_tool_calls[idx]["function"]["arguments"] += (
                                        tc.function.arguments
                                    )

                    # Check for finish
                    if chunk.choices[0].finish_reason in ("stop", "tool_calls"):
                        # Final usage from this response
                        if hasattr(chunk, "usage") and chunk.usage:
                            round_usage.add(GLMProvider.parse_usage(chunk))

            except Exception as e:
                yield (AgentEvent.ERROR, f"Stream error: {e}")
                return

            self.state.usage.add(round_usage)

            # Build the assistant message
            tool_calls_list = [
                current_tool_calls[i] for i in sorted(current_tool_calls.keys())
            ]

            assistant_msg: dict[str, Any] = {"role": "assistant"}
            if assistant_content:
                assistant_msg["content"] = assistant_content
            if tool_calls_list:
                assistant_msg["tool_calls"] = tool_calls_list

            self.state.messages.append(assistant_msg)

            # No tool calls → done
            if not tool_calls_list:
                yield (AgentEvent.DONE, self.state.usage)
                return

            # Execute tool calls
            for tc in tool_calls_list:
                tool_name = tc["function"]["name"]
                tool_args_str = tc["function"]["arguments"]
                tool_call_id = tc["id"]

                try:
                    tool_args = json.loads(tool_args_str)
                except json.JSONDecodeError:
                    tool_args = {}

                yield (AgentEvent.TOOL_START, {"name": tool_name, "args": tool_args})

                if tool_name in self.tools:
                    try:
                        result = self.tools[tool_name](**tool_args)
                        yield (
                            AgentEvent.TOOL_END,
                            {"name": tool_name, "output": str(result), "is_error": False},
                        )
                        self.state.messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call_id,
                                "content": str(result),
                            }
                        )
                    except Exception as e:
                        error_msg = f"Error executing {tool_name}: {e}"
                        yield (
                            AgentEvent.TOOL_END,
                            {"name": tool_name, "output": error_msg, "is_error": True},
                        )
                        self.state.messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call_id,
                                "content": error_msg,
                            }
                        )
                else:
                    unknown_msg = f"Unknown tool: {tool_name}"
                    yield (
                        AgentEvent.TOOL_END,
                        {"name": tool_name, "output": unknown_msg, "is_error": True},
                    )
                    self.state.messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": unknown_msg,
                        }
                    )

        # Safety: exceeded max rounds
        yield (AgentEvent.ERROR, f"Exceeded max tool rounds ({self.state.max_tool_rounds})")
