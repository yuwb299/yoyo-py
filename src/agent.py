"""Agent core — the main loop that drives conversation with tool calling."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from .provider import APIError, GLMProvider, Usage


class AgentEvent(Enum):
    """Events emitted by the agent during execution."""
    TEXT = "text"              # Streaming text delta
    TOOL_START = "tool_start"  # Tool execution started
    TOOL_END = "tool_end"      # Tool execution finished
    DONE = "done"              # Agent turn complete
    ERROR = "error"            # Error occurred
    INTERRUPTED = "interrupted"  # User interrupted via Ctrl+C


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
    compact_threshold: int = 100000  # Token estimate threshold for auto-compact


class Agent:
    """Self-evolving coding agent with tool-calling loop.

    The agent loop:
    1. Send messages to LLM
    2. If LLM returns tool_calls, execute them and append results
    3. Send updated messages back to LLM
    4. Repeat until LLM returns text only (no more tool calls)
    5. Emit streaming text and tool events to caller
    """

    # Tools that modify state and should require user confirmation
    DESTRUCTIVE_TOOLS = {"bash", "write_file", "edit_file"}

    def __init__(
        self,
        provider: GLMProvider,
        system_prompt: str = "",
        tools: dict[str, Callable] | None = None,
        tool_schemas: list[dict] | None = None,
        max_tool_rounds: int = 20,
        verbose: bool = False,
        confirm_fn: Callable[[str, dict], bool] | None = None,
    ):
        self.provider = provider
        self.system_prompt = system_prompt
        self.tools = tools or {}
        self.tool_schemas = tool_schemas or []
        self.state = AgentState(max_tool_rounds=max_tool_rounds)
        self.verbose = verbose
        self._interrupted = False  # Set to True by Ctrl+C to stop current turn
        self.confirm_fn = confirm_fn  # Optional: ask user before destructive tools

        if self.system_prompt:
            self.state.messages = [
                {"role": "system", "content": self.system_prompt}
            ]

    def interrupt(self) -> None:
        """Signal the agent to stop the current turn (called from Ctrl+C handler)."""
        self._interrupted = True

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
        - (INTERRUPTED, None) — user pressed Ctrl+C
        """
        self._interrupted = False
        self.state.messages.append({"role": "user", "content": user_input})

        for round_num in range(self.state.max_tool_rounds):
            if self._interrupted:
                yield (AgentEvent.INTERRUPTED, None)
                return

            # Auto-compact: if context is too long, summarize old messages
            # This prevents token limit errors on long conversations
            if self._should_compact(self.state.messages, max_tokens=self.state.compact_threshold):
                self.state.messages = self._compact_messages(self.state.messages)

            try:
                response = self.provider.chat(
                    messages=self.state.messages,
                    tools=self.tool_schemas if self.tool_schemas else None,
                    stream=True,
                )
            except APIError as e:
                # Provide actionable hints based on error category
                hint = ""
                if e.category == "rate_limit":
                    hint = " (rate limited — wait a moment and try again)"
                elif e.category == "retry_exhausted":
                    hint = " (all retries failed — the API may be down or rate limiting persistently)"
                elif e.category == "auth":
                    hint = " (check your API key in .env)"
                elif e.category == "connection":
                    hint = " (network issue — check your internet connection)"
                elif e.category == "timeout":
                    hint = " (request timed out — try a shorter prompt)"
                yield (AgentEvent.ERROR, f"{e}{hint}")
                return
            except Exception as e:
                yield (AgentEvent.ERROR, f"Unexpected error: {e}")
                return

            # Collect the full assistant message from the stream
            assistant_content = ""
            tool_calls_list: list[dict] = []
            current_tool_calls: dict[int, dict] = {}
            round_usage = Usage()

            try:
                for chunk in response:
                    # Check interrupt flag on every chunk
                    if self._interrupted:
                        break

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

            # Handle interrupt: save what we have and stop
            if self._interrupted:
                self.state.usage.add(round_usage)
                # Save partial assistant message so conversation stays consistent
                assistant_msg: dict[str, Any] = {"role": "assistant"}
                if assistant_content:
                    assistant_msg["content"] = assistant_content + "\n[interrupted]"
                else:
                    assistant_msg["content"] = "[interrupted]"
                self.state.messages.append(assistant_msg)
                yield (AgentEvent.INTERRUPTED, None)
                return

            self.state.usage.add(round_usage)

            # Build the assistant message
            tool_calls_list = [
                current_tool_calls[i] for i in sorted(current_tool_calls.keys())
            ]

            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": assistant_content or None,  # Always include content key — some APIs require it
            }
            if tool_calls_list:
                assistant_msg["tool_calls"] = tool_calls_list

            self.state.messages.append(assistant_msg)

            # No tool calls → done
            if not tool_calls_list:
                yield (AgentEvent.DONE, self.state.usage)
                return

            # Execute tool calls
            for tc in tool_calls_list:
                if self._interrupted:
                    yield (AgentEvent.INTERRUPTED, None)
                    return

                tool_name = tc["function"]["name"]
                tool_args_str = tc["function"]["arguments"]
                tool_call_id = tc["id"]

                try:
                    tool_args = json.loads(tool_args_str)
                except json.JSONDecodeError:
                    tool_args = {}

                yield (AgentEvent.TOOL_START, {"name": tool_name, "args": tool_args})

                # Permission check: confirm_fn can deny destructive tools
                if (self.confirm_fn is not None
                        and tool_name in self.DESTRUCTIVE_TOOLS
                        and not self.confirm_fn(tool_name, tool_args)):
                    denied_msg = f"Permission denied: {tool_name} was not approved by user"
                    yield (
                        AgentEvent.TOOL_END,
                        {"name": tool_name, "output": denied_msg, "is_error": True},
                    )
                    self.state.messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": denied_msg,
                        }
                    )
                    continue

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
                    except TypeError as e:
                        # Missing or wrong arguments — common when LLM sends malformed JSON
                        error_msg = f"Error executing {tool_name}: {e} (args received: {tool_args})"
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

    # ── Context auto-compaction ──────────────────────────────────────

    @staticmethod
    def _estimate_tokens(messages: list[dict[str, Any]]) -> int:
        """Rough token estimate: ~3 chars per token (conservative for mixed text).

        Counts both message content and tool_calls arguments — tool-heavy
        conversations can have substantial arguments that the API charges for.
        """
        total_chars = 0
        for m in messages:
            total_chars += len(m.get("content") or "")
            # Tool call arguments consume tokens too — often large JSON blobs
            for tc in m.get("tool_calls", []):
                func = tc.get("function", {})
                total_chars += len(func.get("name", ""))
                total_chars += len(func.get("arguments", ""))
        return max(total_chars // 3, 1) if total_chars else 0

    @staticmethod
    def _should_compact(messages: list[dict[str, Any]], max_tokens: int = 100000) -> bool:
        """Return True if the message list exceeds the token budget."""
        return Agent._estimate_tokens(messages) > max_tokens

    @staticmethod
    def _compact_messages(
        messages: list[dict[str, Any]],
        keep_recent: int = 4,
    ) -> list[dict[str, Any]]:
        """Compact old messages into a summary, keeping system + recent messages.

        Strategy:
        - Always keep the system prompt (first message if role=="system")
        - Keep the last *keep_recent* non-system messages
        - Replace older messages with a single summary
        - Never leave orphaned tool messages — if compaction would split a
          tool-call sequence, the orphaned tool messages (and their preceding
          assistant with tool_calls) are moved into the "old" bucket
        """
        if not messages:
            return messages

        # Separate system prompt from the rest
        system_msgs = []
        rest = list(messages)
        if rest and rest[0].get("role") == "system":
            system_msgs = [rest.pop(0)]

        # If all messages are "recent", nothing to compact
        if len(rest) <= keep_recent:
            return system_msgs + rest

        # Split into old (to summarize) and recent (to keep)
        old = rest[:-keep_recent]
        recent = rest[-keep_recent:]

        # Fix orphaned tool messages: tool messages must be preceded by an
        # assistant message with tool_calls. Walk forward through recent and
        # move any leading orphaned sequence into old.
        # An orphaned sequence looks like: [assistant(w/ tool_calls), tool, ...tool]
        # at the start of recent, or just [tool, ...tool] at the start.
        while recent:
            if recent[0].get("role") == "tool":
                # Orphaned tool message — find the assistant that triggered it
                # (must be the last message in old) and move both to old
                if old and old[-1].get("role") == "assistant" and "tool_calls" in old[-1]:
                    # Move the assistant from old→recent boundary is wrong;
                    # the assistant is in old, the tool is in recent.
                    # Easiest fix: move the tool into old so the pair stays together
                    # in the summary. Then check the next message in recent.
                    old.append(recent.pop(0))
                else:
                    # Tool message with no preceding assistant — just drop it
                    # (shouldn't normally happen, but defensive)
                    recent.pop(0)
            elif (recent[0].get("role") == "assistant"
                  and "tool_calls" in recent[0]
                  and len(recent) > 1
                  and recent[1].get("role") == "tool"):
                # The assistant+tool sequence starts at the beginning of recent.
                # This is actually fine — the sequence is intact. But we need to
                # make sure ALL tool responses for this assistant are in recent.
                # Find how many tool messages follow (they share the same tool_call_ids).
                call_ids = {tc["id"] for tc in recent[0].get("tool_calls", [])}
                i = 1
                while i < len(recent) and recent[i].get("role") == "tool":
                    i += 1
                # If all tool responses for this assistant are present, it's intact
                tool_ids_in_recent = {recent[j].get("tool_call_id") for j in range(1, i) if recent[j].get("role") == "tool"}
                if call_ids.issubset(tool_ids_in_recent):
                    break  # Sequence is intact, stop fixing
                else:
                    # Some tool responses are missing — move the whole sequence to old
                    for _ in range(i):
                        old.append(recent.pop(0))
            else:
                # First message in recent is not a tool or orphaned assistant — we're good
                break

        # Build a simple summary of old messages
        summary_parts = []
        for m in old:
            role = m.get("role", "unknown")
            content = m.get("content") or ""
            # Truncate very long content in summary
            if len(content) > 200:
                content = content[:200] + "..."
            summary_parts.append(f"[{role}]: {content}")

        summary_text = (
            "[Summary of previous conversation]:\n" + "\n".join(summary_parts)
        )
        summary_msg = {"role": "user", "content": summary_text}

        return system_msgs + [summary_msg] + recent
