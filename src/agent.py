"""Agent core — the main loop that drives conversation with tool calling."""

from __future__ import annotations

import asyncio
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
    compact_threshold: int = 80000  # Token estimate threshold for auto-compact


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
    DESTRUCTIVE_TOOLS = {"bash", "write_file", "edit_file", "rename"}

    # Tools that only read data — safe to execute concurrently for speed.
    # When ALL tool calls in a batch are read-only, they run in parallel
    # via asyncio thread pool. If any destructive tool is present, all run
    # sequentially to preserve ordering guarantees.
    READ_ONLY_TOOLS = {"read_file", "search", "list_files", "glob"}

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
                # Always validate compacted messages — _compact_messages has had
                # 3 bugs in 37 days (Days 5, 18, 37). Silent corruption is worse
                # than a visible warning, so we always check.
                issues = self._validate_messages(self.state.messages)
                if issues:
                    import sys
                    print(f"[compact validation] {issues}", file=sys.stderr)

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
                elif e.category == "bad_request":
                    hint = " (API rejected the request — try /compact if context is corrupted, or /clear to start fresh)"
                elif e.category == "timeout":
                    hint = " (request timed out — try a shorter prompt)"
                error_msg = f"{e}{hint}"
                # Append assistant message so conversation stays valid (no consecutive user msgs)
                self.state.messages.append({
                    "role": "assistant",
                    "content": f"[error: {error_msg}]",
                })
                yield (AgentEvent.ERROR, error_msg)
                return
            except Exception as e:
                error_msg = f"Unexpected error: {e}"
                self.state.messages.append({
                    "role": "assistant",
                    "content": f"[error: {error_msg}]",
                })
                yield (AgentEvent.ERROR, error_msg)
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
                error_msg = f"Stream error: {e}"
                # Save partial assistant content if any, so conversation stays valid
                self.state.usage.add(round_usage)
                self.state.messages.append({
                    "role": "assistant",
                    "content": assistant_content + f"\n[error: {error_msg}]" if assistant_content else f"[error: {error_msg}]",
                })
                yield (AgentEvent.ERROR, error_msg)
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

            # Track which tool_call_ids have been answered so we can fill
            # placeholders for unanswered ones on interrupt
            answered_tool_ids: set[str] = set()

            # ── Phase 1: Parse all tool call arguments ──────────────
            # Parse args and check for malformed JSON before any execution.
            # This lets us decide whether to run in parallel or sequential.
            parsed_calls: list[tuple[dict, str, dict | None, str | None]] = []
            # Each entry: (tc_raw, tool_name, tool_args_or_None, error_msg_or_None)
            all_read_only = True
            needs_permission = False
            for tc in tool_calls_list:
                tool_name = tc["function"]["name"]
                tool_args_str = tc["function"]["arguments"]
                if tool_name not in self.READ_ONLY_TOOLS:
                    all_read_only = False
                if (self.confirm_fn is not None
                        and tool_name in self.DESTRUCTIVE_TOOLS):
                    needs_permission = True
                try:
                    tool_args = json.loads(tool_args_str)
                except json.JSONDecodeError:
                    if not tool_args_str:
                        tool_args = {}
                    else:
                        parsed_calls.append((tc, tool_name, None,
                            f"Malformed JSON in tool arguments: {tool_args_str!r}"))
                        continue
                parsed_calls.append((tc, tool_name, tool_args, None))

            # ── Phase 2: Execute tools ──────────────────────────────
            # Run read-only tools in parallel for speed (e.g. reading 3 files
            # at once). Fall back to sequential when destructive tools or
            # permission checks are involved.
            can_parallel = (
                all_read_only
                and not needs_permission
                and not self._interrupted
                and len([p for p in parsed_calls if p[2] is not None]) > 1
            )

            if can_parallel:
                # Parallel execution: yield TOOL_START for all, then execute
                # concurrently, then yield TOOL_END in order.
                executable = []
                for tc, tool_name, tool_args, err in parsed_calls:
                    if self._interrupted:
                        break
                    tool_call_id = tc["id"]
                    if err is not None:
                        # Malformed args — yield error immediately
                        yield (AgentEvent.TOOL_END,
                            {"name": tool_name, "output": err, "is_error": True})
                        self.state.messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": err,
                        })
                        answered_tool_ids.add(tool_call_id)
                        continue
                    yield (AgentEvent.TOOL_START, {"name": tool_name, "args": tool_args})
                    if tool_name in self.tools:
                        executable.append((tc, tool_name, tool_args, tool_call_id))
                    else:
                        unknown_msg = f"Unknown tool: {tool_name}"
                        yield (AgentEvent.TOOL_END,
                            {"name": tool_name, "output": unknown_msg, "is_error": True})
                        self.state.messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": unknown_msg,
                        })
                        answered_tool_ids.add(tool_call_id)

                if executable and not self._interrupted:
                    # Run all executable tools concurrently in a thread pool
                    loop = asyncio.get_event_loop()
                    async def _run_one(tc, tool_name, tool_args, tool_call_id):
                        try:
                            result = await loop.run_in_executor(
                                None, lambda: self.tools[tool_name](**tool_args))
                            return (tool_name, tool_call_id, str(result), False, None)
                        except TypeError as e:
                            error_msg = f"Error executing {tool_name}: {e} (args received: {tool_args})"
                            return (tool_name, tool_call_id, error_msg, True, None)
                        except Exception as e:
                            error_msg = f"Error executing {tool_name}: {e}"
                            return (tool_name, tool_call_id, error_msg, True, None)

                    results = await asyncio.gather(*[
                        _run_one(*args) for args in executable
                    ])

                    # Yield results in original order
                    for tool_name, tool_call_id, output, is_error, _ in results:
                        if self._interrupted:
                            break
                        yield (AgentEvent.TOOL_END,
                            {"name": tool_name, "output": output, "is_error": is_error})
                        self.state.messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": output,
                        })
                        answered_tool_ids.add(tool_call_id)

                # Fill interrupted tool placeholders if needed
                if self._interrupted:
                    unanswered = [
                        t for t in tool_calls_list
                        if t["id"] not in answered_tool_ids
                    ]
                    for t in unanswered:
                        self.state.messages.append({
                            "role": "tool",
                            "tool_call_id": t["id"],
                            "content": "Tool execution skipped: interrupted",
                        })
                    yield (AgentEvent.INTERRUPTED, None)
                    return
            else:
                # Sequential execution (original behavior) — used when
                # destructive tools or permission checks are involved
                for tc, tool_name, tool_args, err in parsed_calls:
                    if self._interrupted:
                        unanswered = [
                            t for t in tool_calls_list
                            if t["id"] not in answered_tool_ids
                        ]
                        for t in unanswered:
                            self.state.messages.append({
                                "role": "tool",
                                "tool_call_id": t["id"],
                                "content": "Tool execution skipped: interrupted",
                            })
                        yield (AgentEvent.INTERRUPTED, None)
                        return

                    tool_call_id = tc["id"]

                    if err is not None:
                        # Malformed JSON args
                        yield (AgentEvent.TOOL_END,
                            {"name": tool_name, "output": err, "is_error": True})
                        self.state.messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": err,
                        })
                        answered_tool_ids.add(tool_call_id)
                        continue

                    yield (AgentEvent.TOOL_START, {"name": tool_name, "args": tool_args})

                    # Permission check: confirm_fn can deny destructive tools
                    if (self.confirm_fn is not None
                            and tool_name in self.DESTRUCTIVE_TOOLS
                            and not self.confirm_fn(tool_name, tool_args)):
                        denied_msg = f"Permission denied: {tool_name} was not approved by user"
                        yield (AgentEvent.TOOL_END,
                            {"name": tool_name, "output": denied_msg, "is_error": True})
                        self.state.messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": denied_msg,
                        })
                        answered_tool_ids.add(tool_call_id)
                        continue

                    if tool_name in self.tools:
                        try:
                            result = self.tools[tool_name](**tool_args)
                            yield (AgentEvent.TOOL_END,
                                {"name": tool_name, "output": str(result), "is_error": False})
                            self.state.messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call_id,
                                "content": str(result),
                            })
                            answered_tool_ids.add(tool_call_id)
                        except TypeError as e:
                            error_msg = f"Error executing {tool_name}: {e} (args received: {tool_args})"
                            yield (AgentEvent.TOOL_END,
                                {"name": tool_name, "output": error_msg, "is_error": True})
                            self.state.messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call_id,
                                "content": error_msg,
                            })
                            answered_tool_ids.add(tool_call_id)
                        except Exception as e:
                            error_msg = f"Error executing {tool_name}: {e}"
                            yield (AgentEvent.TOOL_END,
                                {"name": tool_name, "output": error_msg, "is_error": True})
                            self.state.messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call_id,
                                "content": error_msg,
                            })
                            answered_tool_ids.add(tool_call_id)
                    else:
                        unknown_msg = f"Unknown tool: {tool_name}"
                        yield (AgentEvent.TOOL_END,
                            {"name": tool_name, "output": unknown_msg, "is_error": True})
                        self.state.messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": unknown_msg,
                        })
                        answered_tool_ids.add(tool_call_id)

        # Safety: exceeded max rounds — append assistant message so conversation stays valid
        max_rounds_msg = f"Exceeded max tool rounds ({self.state.max_tool_rounds})"
        self.state.messages.append({
            "role": "assistant",
            "content": f"[error: {max_rounds_msg}]",
        })
        yield (AgentEvent.ERROR, max_rounds_msg)

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
    def _validate_messages(messages: list[dict[str, Any]]) -> list[str]:
        """Validate conversation structure and return a list of issue descriptions.

        Checks for:
        - Consecutive messages with the same role (user or assistant)
        - Tool messages not preceded by an assistant with tool_calls
        - Mismatched tool_call_ids between assistant tool_calls and tool responses
        - Assistant tool_calls without matching tool responses
        - System prompt not at position 0

        Returns an empty list if the conversation is well-formed.
        """
        issues: list[str] = []
        if not messages:
            return issues

        # System prompt must be first if present
        for i, m in enumerate(messages):
            if m.get("role") == "system" and i > 0:
                issues.append(f"System prompt at position {i} (must be first)")

        # Check for consecutive same-role messages and tool-related issues
        pending_tool_ids: set[str] = set()  # tool_call_ids awaiting responses

        for i, m in enumerate(messages):
            role = m.get("role", "unknown")
            prev_role = messages[i - 1].get("role") if i > 0 else None

            # Consecutive user or assistant messages
            if role in ("user", "assistant") and role == prev_role:
                issues.append(
                    f"Consecutive {role} messages at positions {i - 1} and {i}"
                )

            if role == "assistant":
                tool_calls = m.get("tool_calls", [])
                if tool_calls:
                    # Track tool_call_ids that need responses
                    for tc in tool_calls:
                        tc_id = tc.get("id", "")
                        if tc_id:
                            pending_tool_ids.add(tc_id)
                elif not tool_calls and prev_role == "assistant" and messages[i - 1].get("tool_calls"):
                    # This assistant message might be answering tool results — that's fine
                    pass

            elif role == "tool":
                tc_id = m.get("tool_call_id", "")
                # Tool message must either follow the assistant with tool_calls,
                # or follow another tool message (for multi-tool responses)
                if prev_role not in ("assistant", "tool"):
                    issues.append(
                        f"Tool message at position {i} without preceding assistant or tool message"
                    )
                elif prev_role == "assistant" and not messages[i - 1].get("tool_calls"):
                    issues.append(
                        f"Tool message at position {i} without preceding assistant tool_calls"
                    )
                # Check tool_call_id matches
                if tc_id:
                    if tc_id in pending_tool_ids:
                        pending_tool_ids.discard(tc_id)
                    else:
                        issues.append(
                            f"Tool message at position {i} has unmatched tool_call_id '{tc_id}'"
                        )

        # Check for unanswered tool calls
        if pending_tool_ids:
            issues.append(
                f"Unanswered tool_call_ids: {', '.join(sorted(pending_tool_ids))}"
            )

        return issues

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
        # Cap total summary length to avoid blowing up the token budget.
        # Each message contributes up to ~210 chars (200 content + role prefix).
        # With _COMPACT_SUMMARY_MAX=4000, this is ~20 messages worth of context.
        _COMPACT_SUMMARY_MAX = 4000
        _SUMMARY_HEADER = "[Summary of previous conversation]:\n"
        summary_parts = []
        total_len = len(_SUMMARY_HEADER)
        skipped = 0
        for idx, m in enumerate(old):
            role = m.get("role", "unknown")
            content = m.get("content") or ""
            # Include tool call names for assistant messages with tool_calls
            tool_calls = m.get("tool_calls")
            if tool_calls:
                tool_names = [tc.get("function", {}).get("name", "?") for tc in tool_calls]
                content = f"(called: {', '.join(tool_names)})" + (f" {content}" if content else "")
            # Truncate very long content in summary
            if len(content) > 200:
                content = content[:200] + "..."
            part = f"[{role}]: {content}"
            # Check if adding this part would exceed the cap (account for newline)
            if total_len + len(part) + 1 > _COMPACT_SUMMARY_MAX:
                # Once we hit the cap, count remaining messages and stop
                skipped = len(old) - idx
                break
            summary_parts.append(part)
            total_len += len(part) + 1  # +1 for newline

        summary_text = _SUMMARY_HEADER + "\n".join(summary_parts)
        if skipped:
            summary_text += f"\n... ({skipped} more messages not shown)"

        # Choose summary role to avoid consecutive same-role messages:
        # - If recent is empty, the next message will be from the user, so summary
        #   MUST be assistant to prevent consecutive user messages (API rejection).
        # - If recent starts with a user message, summary should be assistant (same reason).
        # - Otherwise (recent starts with assistant/tool), user role is fine.
        if not recent:
            summary_role = "assistant"
        else:
            first_recent_role = recent[0].get("role")
            summary_role = "assistant" if first_recent_role == "user" else "user"
        summary_msg = {"role": summary_role, "content": summary_text}

        return system_msgs + [summary_msg] + recent
