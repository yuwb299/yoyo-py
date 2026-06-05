"""Tests that /version appears in tab completion and slash command list."""

from src.repl import _SLASH_COMMANDS


def test_version_in_slash_commands():
    """'/version' must appear in the _SLASH_COMMANDS list for tab completion."""
    assert "/version" in _SLASH_COMMANDS, (
        "/version is missing from _SLASH_COMMANDS — tab completion won't suggest it"
    )


def test_all_registered_commands_have_tab_completion():
    """Every registered command should appear in _SLASH_COMMANDS for discoverability.

    This is a completeness check — if a command is registered but not in the
    tab completion list, users can't discover it via tab.
    """
    from src.repl import CommandRegistry

    # Build a minimal registry to get all command names
    # We can't build the full registry without a provider, but we can check
    # that known commands are all in _SLASH_COMMANDS
    known_commands = [
        "help", "quit", "exit", "clear", "redo", "last", "copy",
        "resume", "compact", "cd", "model", "revert",
        "diff", "log", "commit", "undo", "review", "pr",
        "tree", "init", "health", "test", "fix", "edit",
        "status", "tokens", "cost", "history", "search", "grep", "system", "env",
        "config", "list-providers", "think", "version",
        "save", "load", "export", "remember", "memories", "forget",
        "skills", "commands",
    ]
    for cmd in known_commands:
        assert f"/{cmd}" in _SLASH_COMMANDS, (
            f"/{cmd} is registered but missing from _SLASH_COMMANDS tab completion"
        )
