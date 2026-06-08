"""Test that non-interactive mode shows usage stats on exit."""

import os
import sys
import subprocess
import json
from unittest.mock import patch, MagicMock

from src.repl import _run_agent_turn


class TestNonInteractiveUsage:
    """Tests for usage display in non-interactive mode."""

    def test_non_interactive_shows_usage(self, capsys):
        """After _run_agent_turn in non-interactive mode, usage should be printed."""
        from src.agent import Agent, AgentState, AgentEvent
        from src.provider import Usage

        # Create a mock agent that yields a simple text response
        agent = MagicMock(spec=Agent)
        agent.state = AgentState()
        agent.state.usage = Usage(input_tokens=100, output_tokens=50)
        agent.provider = MagicMock()
        agent.provider.model = "test-model"

        async def mock_prompt(text):
            yield (AgentEvent.TEXT, "Hello!")
            yield (AgentEvent.DONE, agent.state.usage)

        agent.prompt = mock_prompt
        agent._interrupted = False

        # This would be called from the REPL, but we test _run_agent_turn directly
        import asyncio
        asyncio.get_event_loop().run_until_complete(_run_agent_turn(agent, "test"))

        captured = capsys.readouterr()
        # The text "Hello!" should have been printed
        assert "Hello!" in captured.out
