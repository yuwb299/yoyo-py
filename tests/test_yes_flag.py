"""Tests for --yes flag and REPL confirmation integration.

The --yes flag auto-approves all destructive tool calls.
Without --yes, the REPL prompts the user for confirmation before
bash, write_file, and edit_file execute.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from src.agent import Agent, AgentEvent
from src.provider import GLMProvider


def _make_chunk(content=None, tool_calls=None, finish_reason=None, usage=None):
    """Create a mock stream chunk."""
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
    """Collect all events from an async generator."""
    events = []
    async for event in agent.prompt(user_input):
        events.append(event)
    return events


class TestYesFlag:
    """Test the --yes flag behavior."""

    def test_yes_flag_auto_approves_all(self):
        """With --yes, a confirm_fn that always returns True is wired up."""
        from src.repl import _make_confirm_fn

        # --yes should produce a confirm_fn that always returns True
        confirm_fn = _make_confirm_fn(auto_approve=True)
        assert confirm_fn("bash", {"command": "rm -rf /"}) is True
        assert confirm_fn("write_file", {"path": "/etc/passwd", "content": "pwned"}) is True
        assert confirm_fn("edit_file", {"path": "important.py", "old_string": "x", "new_string": "y"}) is True

    def test_confirm_fn_rejects_destructive(self):
        """Without --yes, user can reject a destructive tool."""
        from src.repl import _make_confirm_fn

        # Simulate user saying "no"
        confirm_fn = _make_confirm_fn(auto_approve=False, input_fn=lambda _: "n")
        assert confirm_fn("bash", {"command": "rm -rf /"}) is False

    def test_confirm_fn_approves_destructive_on_yes(self):
        """Without --yes, user can approve a destructive tool by typing y/yes."""
        from src.repl import _make_confirm_fn

        confirm_fn = _make_confirm_fn(auto_approve=False, input_fn=lambda _: "y")
        assert confirm_fn("bash", {"command": "echo hi"}) is True

    def test_confirm_fn_case_insensitive(self):
        """y/Y/yes/YES all approve; n/N/no/NO all deny."""
        from src.repl import _make_confirm_fn

        for answer in ("y", "Y", "yes", "YES"):
            confirm_fn = _make_confirm_fn(auto_approve=False, input_fn=lambda _, a=answer: a)
            assert confirm_fn("bash", {"command": "echo"}) is True, f"Expected True for answer '{answer}'"

        for answer in ("n", "N", "no", "NO"):
            confirm_fn = _make_confirm_fn(auto_approve=False, input_fn=lambda _, a=answer: a)
            assert confirm_fn("bash", {"command": "echo"}) is False, f"Expected False for answer '{answer}'"

    def test_confirm_fn_default_is_reject(self):
        """Empty input (just Enter) defaults to reject for safety."""
        from src.repl import _make_confirm_fn

        confirm_fn = _make_confirm_fn(auto_approve=False, input_fn=lambda _: "")
        assert confirm_fn("bash", {"command": "rm -rf /"}) is False

    def test_confirm_fn_not_called_for_read_only(self):
        """confirm_fn should never be called for read_file, search, list_files."""
        from src.repl import _make_confirm_fn

        calls = []
        def track_input(prompt):
            calls.append(prompt)
            return "y"

        confirm_fn = _make_confirm_fn(auto_approve=False, input_fn=track_input)
        # These tools are not in DESTRUCTIVE_TOOLS, so Agent never calls confirm_fn for them
        # Just verify the constant is correct
        assert "read_file" not in Agent.DESTRUCTIVE_TOOLS
        assert "search" not in Agent.DESTRUCTIVE_TOOLS
        assert "list_files" not in Agent.DESTRUCTIVE_TOOLS


class TestConfirmFnIntegration:
    """Integration test: confirm_fn works through the agent loop."""

    def test_auto_approve_allows_bash(self):
        """With auto_approve=True, bash executes normally."""
        mock_provider = MagicMock(spec=GLMProvider)
        tc = _make_tool_call_delta(0, id="tc1", name="bash", arguments='{"command": "echo hi"}')
        mock_provider.chat.side_effect = [
            iter([_make_chunk(tool_calls=[tc], finish_reason="tool_calls")]),
            iter([_make_chunk(content="Done!", finish_reason="stop")]),
        ]

        bash_mock = MagicMock(return_value="hi\n")
        tools = {"bash": bash_mock}
        from src.repl import _make_confirm_fn
        confirm_fn = _make_confirm_fn(auto_approve=True)
        agent = Agent(provider=mock_provider, tools=tools, tool_schemas=[], confirm_fn=confirm_fn)

        events = asyncio.get_event_loop().run_until_complete(
            _collect_events(agent, "run a command")
        )

        bash_mock.assert_called_once()
        tool_end_events = [(e, d) for e, d in events if e == AgentEvent.TOOL_END]
        assert len(tool_end_events) == 1
        assert tool_end_events[0][1]["is_error"] is False
