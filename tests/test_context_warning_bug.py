"""Tests for _show_context_warning — verifies it doesn't crash and works correctly."""

import pytest
from unittest.mock import MagicMock, patch

from src.agent import Agent, AgentState
from src.repl import _show_context_warning


def _make_agent(model="glm-5.1", msg_count=5, token_chars=50000):
    """Create a mock Agent with enough state for _show_context_warning."""
    provider = MagicMock()
    provider.model = model
    agent = Agent.__new__(Agent)
    agent.provider = provider
    agent.state = AgentState()
    # Add messages with enough content to exceed 60% context
    for i in range(msg_count):
        agent.state.messages.append({
            "role": "user" if i % 2 == 0 else "assistant",
            "content": "x" * token_chars,
        })
    return agent


def test_show_context_warning_does_not_crash():
    """_show_context_warning should not crash (was crashing due to wrong function name and missing attr)."""
    agent = _make_agent(model="glm-5.1", msg_count=6, token_chars=50000)
    # This should not raise AttributeError or NameError
    _show_context_warning(agent)


def test_show_context_warning_no_output_under_60_percent():
    """No warning should be printed when context usage < 60%."""
    agent = _make_agent(model="glm-5.1", msg_count=2, token_chars=100)
    with patch("builtins.print") as mock_print:
        _show_context_warning(agent)
        # Should not print anything when usage is low
        mock_print.assert_not_called()


def test_show_context_warning_output_over_60_percent():
    """Warning should be printed when context usage >= 60%."""
    agent = _make_agent(model="glm-5.1", msg_count=6, token_chars=50000)
    with patch("builtins.print") as mock_print:
        _show_context_warning(agent)
        # Should print a context warning
        assert mock_print.called
        output = mock_print.call_args[0][0]
        assert "context:" in output
