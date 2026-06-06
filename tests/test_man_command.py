"""Tests for /man command — per-command help documentation."""

import pytest
from unittest.mock import MagicMock, patch

from src.repl import CommandRegistry


class TestManCommand:
    """Test /man <command> shows focused help for a specific command."""

    def test_man_shows_help_for_known_command(self):
        """/man test should show help text for the /test command."""
        from src.repl import _MAN_PAGES
        assert "test" in _MAN_PAGES
        assert "pytest" in _MAN_PAGES["test"] or "test" in _MAN_PAGES["test"].lower()

    def test_man_shows_error_for_unknown_command(self):
        """/man unknown should show error message."""
        from src.repl import _format_man_page
        result = _format_man_page("nonexistent_cmd")
        assert "no help" in result.lower() or "not found" in result.lower()

    def test_man_without_args_shows_usage(self):
        """/man without args should show usage hint."""
        from src.repl import _format_man_page
        result = _format_man_page("")
        assert "usage" in result.lower() or "command" in result.lower()

    def test_man_pages_covers_key_commands(self):
        """Man pages should exist for the most important commands."""
        from src.repl import _MAN_PAGES
        important = ["test", "health", "fix", "commit", "review", "diff",
                      "status", "config", "model", "compact", "export",
                      "search", "grep", "think"]
        for cmd in important:
            assert cmd in _MAN_PAGES, f"Missing man page for /{cmd}"

    def test_man_page_has_usage_line(self):
        """Each man page should have a 'Usage:' section."""
        from src.repl import _MAN_PAGES
        for cmd, text in _MAN_PAGES.items():
            assert "usage" in text.lower(), f"/{cmd} man page missing 'Usage' section"


class TestManCommandRegistry:
    """Test /man is wired into the command registry."""

    def test_man_in_registry(self):
        """/man is a registered command."""
        from src.repl import _build_command_registry, CommandRegistry
        from src.agent import Agent
        from src.provider import GLMProvider

        agent = MagicMock(spec=Agent)
        provider = MagicMock(spec=GLMProvider)
        provider.model = "test-model"
        provider.reasoning_effort = None
        skills = MagicMock()
        skills.count.return_value = 0

        registry = _build_command_registry(agent, provider, skills)
        result = registry.dispatch("/man test", {})
        assert result is not None
        assert "test" in result.output.lower() or "pytest" in result.output.lower()

    def test_man_unknown_returns_error(self):
        """/man nonexistent returns error message."""
        from src.repl import _build_command_registry
        from src.agent import Agent
        from src.provider import GLMProvider

        agent = MagicMock(spec=Agent)
        provider = MagicMock(spec=GLMProvider)
        provider.model = "test-model"
        provider.reasoning_effort = None
        skills = MagicMock()
        skills.count.return_value = 0

        registry = _build_command_registry(agent, provider, skills)
        result = registry.dispatch("/man blargh", {})
        assert result is not None
        assert "no help" in result.output.lower() or "not found" in result.output.lower()

    def test_man_empty_returns_usage(self):
        """/man with no args returns usage hint."""
        from src.repl import _build_command_registry
        from src.agent import Agent
        from src.provider import GLMProvider

        agent = MagicMock(spec=Agent)
        provider = MagicMock(spec=GLMProvider)
        provider.model = "test-model"
        provider.reasoning_effort = None
        skills = MagicMock()
        skills.count.return_value = 0

        registry = _build_command_registry(agent, provider, skills)
        result = registry.dispatch("/man", {})
        assert result is not None
