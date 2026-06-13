"""Tests for NO_COLOR and color control support."""

import os
import pytest
from src.repl import RESET, GREEN, RED, YELLOW, CYAN, DIM, BOLD, MAGENTA


class TestColorControl:
    """Test that color output respects NO_COLOR environment variable."""

    def test_color_constants_are_strings(self):
        """Color constants should be ANSI escape strings."""
        assert RESET.startswith("\x1b[")
        assert GREEN.startswith("\x1b[")
        assert RED.startswith("\x1b[")

    def test_no_color_env_disables_colors(self, monkeypatch):
        """When NO_COLOR is set, color constants should be empty strings."""
        # Re-import with NO_COLOR set
        monkeypatch.setenv("NO_COLOR", "1")
        # Need to re-import the module to pick up the env var
        import importlib
        import src.repl as repl_mod
        importlib.reload(repl_mod)
        # After reload, color constants should be empty
        assert repl_mod.RESET == ""
        assert repl_mod.GREEN == ""
        assert repl_mod.RED == ""

    def test_no_color_unset_keeps_colors(self, monkeypatch):
        """When NO_COLOR is not set, color constants should be ANSI codes."""
        monkeypatch.delenv("NO_COLOR", raising=False)
        import importlib
        import src.repl as repl_mod
        importlib.reload(repl_mod)
        assert repl_mod.RESET.startswith("\x1b[")
        assert repl_mod.GREEN.startswith("\x1b[")
