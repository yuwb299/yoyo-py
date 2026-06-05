"""Tests for /version command."""

import pytest
from unittest.mock import MagicMock

from src.repl import CommandRegistry, CommandResult, _build_command_registry
from src.agent import Agent, AgentState
from src.provider import GLMProvider


@pytest.fixture
def registry():
    """Build a command registry with a mock agent and provider."""
    provider = MagicMock(spec=GLMProvider)
    provider.model = "test-model"
    provider.reasoning_effort = None
    provider.api_key = "fake-key"
    provider.temperature = None
    provider.max_tokens = None
    provider.top_p = None
    provider.base_url = "https://api.example.com"
    provider._provider_name = "test"

    agent = MagicMock(spec=Agent)
    agent.state = MagicMock(spec=AgentState)
    agent.state.messages = [{"role": "system", "content": "test"}]
    agent.state.usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    from src.repl import SkillSet
    skills = SkillSet()

    return _build_command_registry(agent, provider, skills)


class TestVersionCommand:
    """Tests for /version slash command."""

    def test_version_shows_version(self, registry):
        result = registry.dispatch("/version", {})
        assert result is not None
        assert "yoyo-py" in result.output

    def test_version_shows_model(self, registry):
        result = registry.dispatch("/version", {})
        assert "test-model" in result.output

    def test_version_shows_python_version(self, registry):
        result = registry.dispatch("/version", {})
        assert "Python" in result.output

    def test_version_is_registered(self, registry):
        """version command is in the registry."""
        assert "version" in registry.list_commands()
