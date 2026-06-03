"""Tests for the command registry system.

The registry maps slash command names to handler functions, making
the dispatch logic testable and extensible without modifying the
main REPL loop.
"""

import os
import pytest
from unittest.mock import MagicMock, patch

from src.repl import (
    CommandRegistry,
    CommandResult,
    command_handler,
)


# ── CommandRegistry tests ──────────────────────────────────────────────


class TestCommandRegistry:
    """Tests for the CommandRegistry class."""

    def test_register_and_dispatch(self):
        """Can register a command and dispatch it."""
        registry = CommandRegistry()

        @registry.register("hello")
        def handle_hello(line: str, ctx: dict) -> CommandResult:
            return CommandResult(output="Hello!")

        result = registry.dispatch("/hello", {})
        assert result.output == "Hello!"

    def test_dispatch_unknown_command(self):
        """Unknown commands return None."""
        registry = CommandRegistry()
        result = registry.dispatch("/unknown", {})
        assert result is None

    def test_dispatch_preserves_case_in_args(self):
        """Dispatch passes original line to handler (case preserved)."""
        registry = CommandRegistry()

        @registry.register("echo")
        def handle_echo(line: str, ctx: dict) -> CommandResult:
            return CommandResult(output=line)

        result = registry.dispatch("/echo Hello World", {})
        assert result.output == "/echo Hello World"

    def test_register_multiple_commands(self):
        """Can register multiple commands."""
        registry = CommandRegistry()

        @registry.register("foo")
        def handle_foo(line: str, ctx: dict) -> CommandResult:
            return CommandResult(output="foo")

        @registry.register("bar")
        def handle_bar(line: str, ctx: dict) -> CommandResult:
            return CommandResult(output="bar")

        assert registry.dispatch("/foo", {}).output == "foo"
        assert registry.dispatch("/bar", {}).output == "bar"

    def test_list_commands(self):
        """list_commands returns all registered command names."""
        registry = CommandRegistry()

        @registry.register("alpha")
        def handle_alpha(line: str, ctx: dict) -> CommandResult:
            return CommandResult(output="a")

        @registry.register("beta")
        def handle_beta(line: str, ctx: dict) -> CommandResult:
            return CommandResult(output="b")

        names = registry.list_commands()
        assert "alpha" in names
        assert "beta" in names
        assert len(names) == 2

    def test_dispatch_with_prefix_match(self):
        """Commands with arguments (e.g. /commit msg) dispatch correctly."""
        registry = CommandRegistry()

        @registry.register("commit")
        def handle_commit(line: str, ctx: dict) -> CommandResult:
            msg = line[7:].strip() if len(line) > 7 else ""
            return CommandResult(output=f"committed: {msg}")

        result = registry.dispatch("/commit fix bug", {})
        assert result.output == "committed: fix bug"

    def test_overwrite_existing_command(self):
        """Registering the same name twice overwrites the previous handler."""
        registry = CommandRegistry()

        @registry.register("test")
        def handle_v1(line: str, ctx: dict) -> CommandResult:
            return CommandResult(output="v1")

        @registry.register("test")
        def handle_v2(line: str, ctx: dict) -> CommandResult:
            return CommandResult(output="v2")

        assert registry.dispatch("/test", {}).output == "v2"


class TestCommandResult:
    """Tests for the CommandResult dataclass."""

    def test_simple_output(self):
        """CommandResult with just output."""
        result = CommandResult(output="hello")
        assert result.output == "hello"
        assert result.agent_prompt is None
        assert result.done is False

    def test_agent_prompt(self):
        """CommandResult that should trigger an agent turn."""
        result = CommandResult(output="", agent_prompt="review this code")
        assert result.agent_prompt == "review this code"

    def test_done_flag(self):
        """CommandResult with done=True signals REPL exit."""
        result = CommandResult(output="bye", done=True)
        assert result.done is True


class TestCommandHandlerContext:
    """Tests that command handlers receive correct context."""

    def test_handler_receives_context(self):
        """Handlers receive ctx dict with agent state."""
        registry = CommandRegistry()

        @registry.register("check")
        def handle_check(line: str, ctx: dict) -> CommandResult:
            model = ctx.get("model", "unknown")
            return CommandResult(output=f"model: {model}")

        result = registry.dispatch("/check", {"model": "glm-5"})
        assert result.output == "model: glm-5"

    def test_handler_can_access_messages(self):
        """Handlers can access conversation history via ctx."""
        registry = CommandRegistry()

        @registry.register("count")
        def handle_count(line: str, ctx: dict) -> CommandResult:
            messages = ctx.get("messages", [])
            return CommandResult(output=f"{len(messages)} messages")

        result = registry.dispatch("/count", {"messages": [1, 2, 3]})
        assert result.output == "3 messages"


class TestCommandHandlerDecorator:
    """Tests for the @command_handler decorator."""

    def test_decorator_registers_command(self):
        """@command_handler registers the function as a command handler."""
        registry = CommandRegistry()

        @command_handler(registry, "greet")
        def handle_greet(line: str, ctx: dict) -> CommandResult:
            return CommandResult(output="hi")

        result = registry.dispatch("/greet", {})
        assert result.output == "hi"

    def test_decorator_with_aliases(self):
        """@command_handler supports aliases."""
        registry = CommandRegistry()

        @command_handler(registry, "quit", aliases=["exit"])
        def handle_quit(line: str, ctx: dict) -> CommandResult:
            return CommandResult(output="bye", done=True)

        assert registry.dispatch("/quit", {}).done is True
        assert registry.dispatch("/exit", {}).done is True
