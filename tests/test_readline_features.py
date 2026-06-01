"""Tests for readline history and tab completion features."""

import os

import pytest


class TestSlashCompletion:
    """Tests for slash command tab completion."""

    def test_completes_slash_prefix(self):
        """Completing '/' should return all slash commands."""
        from src.repl import _slash_completer

        results = []
        state = 0
        while True:
            r = _slash_completer("/", state)
            if r is None:
                break
            results.append(r)
            state += 1
        assert len(results) > 10
        assert all(r.startswith("/") for r in results)

    def test_completes_specific_prefix(self):
        """Completing '/co' should match /commit, /config, /copy, /cost, /commands."""
        from src.repl import _slash_completer

        results = []
        state = 0
        while True:
            r = _slash_completer("/co", state)
            if r is None:
                break
            results.append(r)
            state += 1
        assert "/commit" in results
        assert "/config" in results
        assert "/copy" in results
        assert "/cost" in results
        assert "/commands" in results

    def test_exact_match(self):
        """Completing '/help' should return just /help."""
        from src.repl import _slash_completer

        assert _slash_completer("/help", 0) == "/help"
        assert _slash_completer("/help", 1) is None

    def test_no_match(self):
        """Completing non-matching text should return None."""
        from src.repl import _slash_completer

        assert _slash_completer("/xyz", 0) is None

    def test_non_slash_text_no_match(self):
        """Non-slash text should not match slash commands."""
        from src.repl import _slash_completer

        assert _slash_completer("hello", 0) is None
        assert _slash_completer("", 0) is None

    def test_state_exhaustion(self):
        """State beyond available matches should return None."""
        from src.repl import _slash_completer

        # Exhaust all /c matches
        state = 0
        while _slash_completer("/c", state) is not None:
            state += 1
        assert _slash_completer("/c", state) is None

    def test_completes_all_known_commands(self):
        """Every command in _SLASH_COMMANDS should be completable."""
        from src.repl import _SLASH_COMMANDS, _slash_completer

        for cmd in _SLASH_COMMANDS:
            assert _slash_completer(cmd, 0) == cmd, f"{cmd} not completable"


class TestReadlineHistory:
    """Tests for readline history file management."""

    def test_setup_readline_idempotent(self):
        """Calling _setup_readline multiple times should not crash."""
        from src.repl import _setup_readline

        _setup_readline()
        _setup_readline()

    def test_save_readline_history_no_crash(self):
        """_save_readline_history should never crash."""
        from src.repl import _save_readline_history

        _save_readline_history()

    def test_history_file_in_home_dir(self):
        """History file should be in the user's home directory."""
        from src.repl import _HISTORY_FILE

        home = os.path.expanduser("~")
        assert _HISTORY_FILE.startswith(home)
        assert _HISTORY_FILE.endswith(".yoyo_history")

    def test_history_max_is_reasonable(self):
        """History max length should be positive and reasonable."""
        from src.repl import _HISTORY_MAX

        assert 100 <= _HISTORY_MAX <= 10000

    def test_slash_commands_list_complete(self):
        """The slash commands list should contain all known commands."""
        from src.repl import _SLASH_COMMANDS

        assert len(_SLASH_COMMANDS) > 10
        assert all(c.startswith("/") for c in _SLASH_COMMANDS)
        # Spot check important commands exist
        for cmd in ["/help", "/quit", "/exit", "/clear", "/status", "/commit", "/diff"]:
            assert cmd in _SLASH_COMMANDS, f"{cmd} missing from _SLASH_COMMANDS"

    def test_slash_commands_sorted(self):
        """Slash commands should be sorted for consistent completion order."""
        from src.repl import _SLASH_COMMANDS

        assert _SLASH_COMMANDS == sorted(_SLASH_COMMANDS)
