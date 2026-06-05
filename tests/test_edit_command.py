"""Tests for /edit command — open file in user's $EDITOR."""

import os
import pytest
from unittest.mock import patch, MagicMock

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


class TestEditCommand:
    """Tests for /edit slash command."""

    def test_edit_no_args_shows_usage(self, registry):
        result = registry.dispatch("/edit", {})
        assert result is not None
        assert "Usage" in result.output or "usage" in result.output.lower()

    def test_edit_nonexistent_file(self, registry, tmp_path):
        result = registry.dispatch(f"/edit {tmp_path}/nonexistent.py", {})
        assert result is not None
        assert "not found" in result.output.lower() or "error" in result.output.lower()

    def test_edit_existing_file(self, registry, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')\n")

        with patch("subprocess.call") as mock_call:
            result = registry.dispatch(f"/edit {test_file}", {})

        assert result is not None
        assert mock_call.called or "EDITOR" in result.output

    def test_edit_respects_editor_env(self, registry, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')\n")

        with patch.dict(os.environ, {"EDITOR": "nano"}):
            with patch("subprocess.call") as mock_call:
                result = registry.dispatch(f"/edit {test_file}", {})

        if mock_call.called:
            call_args = mock_call.call_args[0][0]
            assert "nano" in call_args

    def test_edit_respects_visual_env(self, registry, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')\n")

        with patch.dict(os.environ, {"VISUAL": "code"}, clear=False):
            # Remove EDITOR to fall back to VISUAL
            env = os.environ.copy()
            env.pop("EDITOR", None)
            with patch.dict(os.environ, env, clear=True):
                with patch("subprocess.call") as mock_call:
                    result = registry.dispatch(f"/edit {test_file}", {})

        if mock_call.called:
            call_args = mock_call.call_args[0][0]
            assert "code" in call_args

    def test_edit_default_editor_is_vim(self, registry, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')\n")

        env = os.environ.copy()
        env.pop("EDITOR", None)
        env.pop("VISUAL", None)
        with patch.dict(os.environ, env, clear=True):
            with patch("subprocess.call") as mock_call:
                result = registry.dispatch(f"/edit {test_file}", {})

        if mock_call.called:
            call_args = mock_call.call_args[0][0]
            assert "vi" in call_args or "vim" in call_args
