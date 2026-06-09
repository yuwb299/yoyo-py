"""Tests for /cat slash command — quick file viewing without the agent."""

import os
import tempfile

import pytest
from src.repl import CommandRegistry, CommandResult, _build_command_registry
from src.agent import Agent
from src.provider import GLMProvider
from src.skills import SkillSet


def _make_registry(tmpdir=None):
    """Helper to create a registry with a mock provider."""
    provider = object.__new__(GLMProvider)
    provider.model = "test-model"
    provider.base_url = "https://example.com"
    provider.api_key = "test-key"
    provider.max_tokens = None
    provider.temperature = None
    provider.top_p = None
    provider.reasoning_effort = None
    provider._provider_name = "test"

    agent = Agent(provider=provider, system_prompt="test")

    skills = SkillSet()
    return _build_command_registry(agent, provider, skills)


class TestCatCommand:
    """Test /cat command for quick file viewing."""

    def test_cat_registered(self):
        """The /cat command is registered."""
        registry = _make_registry()
        assert "cat" in registry._handlers

    def test_cat_shows_file_content(self):
        """Displays file content with line numbers."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello\nworld\n")
            f.flush()
            path = f.name

        try:
            registry = _make_registry()
            result = registry.dispatch(f"/cat {path}", {})
            assert result is not None
            assert "hello" in result.output
            assert "world" in result.output
        finally:
            os.unlink(path)

    def test_cat_with_line_range(self):
        """Supports offset and limit to read specific line ranges."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            for i in range(100):
                f.write(f"line {i + 1}\n")
            f.flush()
            path = f.name

        try:
            registry = _make_registry()
            # /cat path 10 5 means offset=10, limit=5
            result = registry.dispatch(f"/cat {path} 10 5", {})
            assert result is not None
            assert "line 10" in result.output
            assert "line 14" in result.output
            # Should NOT contain line 15 (only 5 lines from offset 10)
            assert "line 15" not in result.output
        finally:
            os.unlink(path)

    def test_cat_missing_file(self):
        """Shows error for non-existent file."""
        registry = _make_registry()
        result = registry.dispatch("/cat /nonexistent/path.txt", {})
        assert result is not None
        assert "not found" in result.output.lower() or "error" in result.output.lower()

    def test_cat_no_args(self):
        """Shows usage hint when no file path given."""
        registry = _make_registry()
        result = registry.dispatch("/cat", {})
        assert result is not None
        assert "usage" in result.output.lower()

    def test_cat_binary_file(self):
        """Shows error for binary files."""
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".bin", delete=False) as f:
            f.write(b"\x00\x01\x02\x03\xff\xfe")
            path = f.name

        try:
            registry = _make_registry()
            result = registry.dispatch(f"/cat {path}", {})
            assert result is not None
            assert "binary" in result.output.lower() or "error" in result.output.lower()
        finally:
            os.unlink(path)

    def test_cat_tab_completion(self):
        """The 'cat' command appears in tab completion."""
        from src.repl import _SLASH_COMMANDS
        assert "/cat" in _SLASH_COMMANDS
