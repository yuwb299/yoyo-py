"""Tests for /provider command — switch provider presets at runtime."""

from __future__ import annotations

import os
import pytest
from unittest.mock import patch, MagicMock

from src.repl import _build_command_registry
from src.provider import GLMProvider


def _make_provider(**kwargs):
    """Create a GLMProvider with defaults for testing."""
    defaults = {
        "api_key": "test-key-1234567890",
        "model": "test-model",
        "base_url": "https://api.test.com/v1",
    }
    defaults.update(kwargs)
    return GLMProvider(**defaults)


def _make_registry(provider=None):
    """Build a command registry with a test provider."""
    from src.agent import Agent
    from src.skills import SkillSet

    if provider is None:
        provider = _make_provider()
    skills = SkillSet()
    agent = Agent(provider=provider, system_prompt="test")
    return _build_command_registry(agent, provider, skills)


class TestProviderCommand:
    """Tests for the /provider slash command."""

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai-key-12345"})
    def test_provider_switch_to_openai(self):
        """Switch to openai provider preset."""
        provider = _make_provider()
        registry = _make_registry(provider)

        result = registry.dispatch("/provider openai", {})
        assert result is not None
        assert "openai" in result.output.lower()
        assert "switched" in result.output.lower()

    @patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test-deepseek-key-12345"})
    def test_provider_switch_to_deepseek(self):
        """Switch to deepseek provider preset."""
        provider = _make_provider()
        registry = _make_registry(provider)

        result = registry.dispatch("/provider deepseek", {})
        assert result is not None
        assert "deepseek" in result.output.lower()
        assert "switched" in result.output.lower()

    def test_provider_no_args_shows_current(self):
        """No arguments shows current provider info."""
        provider = _make_provider()
        registry = _make_registry(provider)

        result = registry.dispatch("/provider", {})
        assert result is not None
        assert "current" in result.output.lower() or "provider" in result.output.lower()

    def test_provider_unknown_shows_available(self):
        """Unknown provider shows available providers."""
        provider = _make_provider()
        registry = _make_registry(provider)

        result = registry.dispatch("/provider nonexistent", {})
        assert result is not None
        assert "unknown" in result.output.lower() or "available" in result.output.lower()

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai-key-12345"})
    def test_provider_switch_updates_model(self):
        """Switching provider updates the model."""
        provider = _make_provider()
        registry = _make_registry(provider)

        old_model = provider.model
        result = registry.dispatch("/provider openai", {})
        assert result is not None
        # Model should have changed to openai default
        assert provider.model != old_model or "openai" in provider.model.lower() or "gpt" in provider.model.lower()

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai-key-12345"})
    def test_provider_switch_with_custom_model(self):
        """Switch provider with a specific model."""
        provider = _make_provider()
        registry = _make_registry(provider)

        result = registry.dispatch("/provider openai gpt-4o-mini", {})
        assert result is not None
        assert provider.model == "gpt-4o-mini"

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai-key-12345"})
    def test_provider_switch_preserves_history_by_default(self):
        """Switching provider preserves conversation history by default."""
        from src.agent import Agent
        from src.skills import SkillSet

        provider = _make_provider()
        skills = SkillSet()
        agent = Agent(provider=provider, system_prompt="test")
        agent.state.messages.append({"role": "user", "content": "hello"})
        registry = _build_command_registry(agent, provider, skills)

        result = registry.dispatch("/provider openai", {})
        assert result is not None
        # History should be preserved
        assert len(agent.state.messages) > 1  # system + user still there

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-openai-key-12345"})
    def test_provider_switch_with_clear(self):
        """Switching provider with --clear clears history."""
        from src.agent import Agent
        from src.skills import SkillSet

        provider = _make_provider()
        skills = SkillSet()
        agent = Agent(provider=provider, system_prompt="test")
        agent.state.messages.append({"role": "user", "content": "hello"})
        registry = _build_command_registry(agent, provider, skills)

        result = registry.dispatch("/provider openai --clear", {})
        assert result is not None
        # Only system prompt should remain
        assert len([m for m in agent.state.messages if m.get("role") != "system"]) == 0

    def test_provider_missing_api_key(self):
        """Switching to provider with missing API key shows error."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove any openai key
            os.environ.pop("OPENAI_API_KEY", None)
            provider = _make_provider()
            registry = _make_registry(provider)

            result = registry.dispatch("/provider openai", {})
            assert result is not None
            assert "error" in result.output.lower() or "key" in result.output.lower() or "failed" in result.output.lower()
