"""Tests for /cd command's system prompt update — specifically git context refresh."""

import os

from src.repl import _update_system_prompt_cwd


class TestUpdateSystemPromptCwd:
    """Tests for _update_system_prompt_cwd — ensuring git context refresh works correctly."""

    def test_updates_cwd_line(self):
        """Should update the 'Current working directory:' line."""
        messages = [{"role": "system", "content": "Current working directory: /old/path\nSome other text"}]
        _update_system_prompt_cwd(messages)
        assert f"Current working directory: {os.getcwd()}" in messages[0]["content"]
        assert "/old/path" not in messages[0]["content"]
        assert "Some other text" in messages[0]["content"]

    def test_no_system_message(self):
        """Should do nothing when no system message exists."""
        messages = [{"role": "user", "content": "hello"}]
        _update_system_prompt_cwd(messages)
        assert messages[0]["content"] == "hello"

    def test_empty_messages(self):
        """Should handle empty message list without error."""
        messages = []
        _update_system_prompt_cwd(messages)

    def test_no_cwd_line(self):
        """Should not modify content if no cwd line found."""
        original = "You are a helpful assistant."
        messages = [{"role": "system", "content": original}]
        _update_system_prompt_cwd(messages)
        assert messages[0]["content"] == original

    def test_git_context_refresh_no_duplicate(self):
        """Git context lines should be replaced, not duplicated.

        This tests the bug where git context lines like 'Branch: main' were
        kept after the fresh git context was inserted, causing duplication.
        """
        # Simulate a system prompt with git context embedded
        content = (
            "You are a coding assistant.\n"
            "Current working directory: /old\n"
            "\n"
            "# Git Context\n"
            "Branch: old-branch\n"
            "Recently changed files:\n"
            "  old_file.py\n"
            "\n"
            "# Loaded Skills\n"
            "some skill content"
        )
        messages = [{"role": "system", "content": content}]
        _update_system_prompt_cwd(messages)
        result = messages[0]["content"]

        # The old git context should be fully replaced
        assert "old-branch" not in result
        assert "old_file.py" not in result
        # Skills section should be preserved
        assert "# Loaded Skills" in result
        assert "some skill content" in result
        # The cwd should be updated
        assert f"Current working directory: {os.getcwd()}" in result

    def test_git_context_at_end_of_prompt(self):
        """Git context at the end of the prompt should be fully replaced."""
        content = (
            "You are a coding assistant.\n"
            "Current working directory: /old\n"
            "\n"
            "# Git Context\n"
            "Branch: test-branch"
        )
        messages = [{"role": "system", "content": content}]
        _update_system_prompt_cwd(messages)
        result = messages[0]["content"]

        # Old branch name should be gone
        assert "test-branch" not in result

    def test_git_context_with_no_following_section(self):
        """Git context followed only by whitespace/empty lines should be replaced."""
        content = (
            "You are a coding assistant.\n"
            "Current working directory: /old\n"
            "\n"
            "# Git Context\n"
            "Branch: feature-x\n"
        )
        messages = [{"role": "system", "content": content}]
        _update_system_prompt_cwd(messages)
        result = messages[0]["content"]

        assert "feature-x" not in result
        assert f"Current working directory: {os.getcwd()}" in result
