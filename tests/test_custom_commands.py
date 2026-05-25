"""Tests for custom slash commands loaded from .yoyo/commands/."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from src.repl import _load_custom_commands, _resolve_custom_command


class TestLoadCustomCommands:
    """Test loading custom command definitions from .yoyo/commands/."""

    def test_load_from_directory(self, tmp_path):
        """Load all .md files from .yoyo/commands/."""
        cmd_dir = tmp_path / ".yoyo" / "commands"
        cmd_dir.mkdir(parents=True)

        (cmd_dir / "review.md").write_text(
            "---\ndescription: Review code changes\n---\nReview the current git diff and suggest improvements."
        )
        (cmd_dir / "deploy.md").write_text(
            "---\ndescription: Deploy to production\n---\nRun the deploy script and check the logs."
        )

        commands = _load_custom_commands(str(tmp_path))
        assert len(commands) == 2
        assert "review" in commands
        assert "deploy" in commands
        assert "Review code changes" in commands["review"]["description"]
        assert "git diff" in commands["review"]["prompt"]

    def test_empty_commands_dir(self, tmp_path):
        """Return empty dict when no commands exist."""
        commands = _load_custom_commands(str(tmp_path))
        assert commands == {}

    def test_nonexistent_dir(self, tmp_path):
        """Return empty dict when .yoyo/commands/ doesn't exist."""
        commands = _load_custom_commands(str(tmp_path / "nonexistent"))
        assert commands == {}

    def test_ignores_non_md_files(self, tmp_path):
        """Only load .md files, ignore others."""
        cmd_dir = tmp_path / ".yoyo" / "commands"
        cmd_dir.mkdir(parents=True)
        (cmd_dir / "review.md").write_text("Review the code.")
        (cmd_dir / "notes.txt").write_text("This is not a command.")
        (cmd_dir / "config.json").write_text("{}")

        commands = _load_custom_commands(str(tmp_path))
        assert len(commands) == 1
        assert "review" in commands

    def test_command_without_frontmatter(self, tmp_path):
        """Command file without YAML frontmatter uses full content as prompt."""
        cmd_dir = tmp_path / ".yoyo" / "commands"
        cmd_dir.mkdir(parents=True)
        (cmd_dir / "hello.md").write_text("Say hello to the user.")

        commands = _load_custom_commands(str(tmp_path))
        assert len(commands) == 1
        assert commands["hello"]["prompt"] == "Say hello to the user."
        assert commands["hello"]["description"] == ""

    def test_command_name_from_filename(self, tmp_path):
        """Command name is derived from the filename (without .md)."""
        cmd_dir = tmp_path / ".yoyo" / "commands"
        cmd_dir.mkdir(parents=True)
        (cmd_dir / "code-review.md").write_text("Review code.")

        commands = _load_custom_commands(str(tmp_path))
        assert "code-review" in commands

    def test_command_with_frontmatter_name_override(self, tmp_path):
        """YAML frontmatter can override the command name."""
        cmd_dir = tmp_path / ".yoyo" / "commands"
        cmd_dir.mkdir(parents=True)
        (cmd_dir / "cr.md").write_text(
            "---\nname: code-review\ndescription: Code review\n---\nReview the code."
        )

        commands = _load_custom_commands(str(tmp_path))
        assert "code-review" in commands
        assert "cr" not in commands


class TestResolveCustomCommand:
    """Test resolving user input to a custom command prompt."""

    def test_resolve_existing_command(self, tmp_path):
        """Resolve a command that exists in .yoyo/commands/."""
        cmd_dir = tmp_path / ".yoyo" / "commands"
        cmd_dir.mkdir(parents=True)
        (cmd_dir / "review.md").write_text(
            "---\ndescription: Review changes\n---\nReview the current git diff."
        )

        result = _resolve_custom_command("review", str(tmp_path))
        assert result is not None
        assert "Review the current git diff." in result

    def test_resolve_nonexistent_command(self, tmp_path):
        """Return None for a command that doesn't exist."""
        result = _resolve_custom_command("nonexistent", str(tmp_path))
        assert result is None

    def test_resolve_command_with_args(self, tmp_path):
        """Custom commands can include {{args}} placeholder for user-provided arguments."""
        cmd_dir = tmp_path / ".yoyo" / "commands"
        cmd_dir.mkdir(parents=True)
        (cmd_dir / "explain.md").write_text("Explain this code: {{args}}")

        result = _resolve_custom_command("explain", str(tmp_path), args="src/agent.py")
        assert result is not None
        assert "src/agent.py" in result

    def test_resolve_command_without_args_placeholder(self, tmp_path):
        """If no {{args}} placeholder but user provides args, they are appended."""
        cmd_dir = tmp_path / ".yoyo" / "commands"
        cmd_dir.mkdir(parents=True)
        (cmd_dir / "review.md").write_text("Review the git diff.")

        result = _resolve_custom_command("review", str(tmp_path), args="extra stuff")
        assert result is not None
        # Without {{args}} placeholder, args are appended after the prompt
        assert "Review the git diff." in result
        assert "extra stuff" in result

    def test_resolve_command_with_no_args(self, tmp_path):
        """Command without {{args}} and no user args works fine."""
        cmd_dir = tmp_path / ".yoyo" / "commands"
        cmd_dir.mkdir(parents=True)
        (cmd_dir / "review.md").write_text("Review the git diff.")

        result = _resolve_custom_command("review", str(tmp_path))
        assert result is not None
        assert result == "Review the git diff."
