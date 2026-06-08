"""Tests for context file refresh on /cd.

When the user changes directory with /cd, the system prompt should
update not just the CWD line and git context, but also the project
context file section — loading the appropriate context file from the
new directory.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from src.repl import _update_system_prompt_cwd, _find_context_file


def _make_system_msg(content: str) -> list[dict]:
    """Create a minimal messages list with a system prompt."""
    return [{"role": "system", "content": content}]


class TestContextRefreshOnCd:
    """Test that project context is refreshed when /cd changes directory."""

    def test_removes_old_context_on_cd(self, tmp_path):
        """Old project context is removed when cd'ing to a dir without one."""
        old_dir = tmp_path / "old"
        old_dir.mkdir()
        (old_dir / "YOYO.md").write_text("# Old project")

        new_dir = tmp_path / "new"
        new_dir.mkdir()

        system = (
            "You are a coding assistant.\n"
            "Current working directory: /tmp/old\n"
            "\n# Project Context (YOYO.md)\n"
            "# Old project\n"
        )
        messages = _make_system_msg(system)

        with patch("os.getcwd", return_value=str(new_dir)):
            with patch("src.repl._find_context_file", return_value=None):
                _update_system_prompt_cwd(messages)

        content = messages[0]["content"]
        assert "Old project" not in content
        assert "Project Context" not in content

    def test_adds_new_context_on_cd(self, tmp_path):
        """New project context is added when cd'ing to a dir with one."""
        new_dir = tmp_path / "new"
        new_dir.mkdir()
        (new_dir / "CLAUDE.md").write_text("# New project")

        system = (
            "You are a coding assistant.\n"
            "Current working directory: /tmp/old\n"
        )
        messages = _make_system_msg(system)

        ctx_path = str(new_dir / "CLAUDE.md")
        with patch("os.getcwd", return_value=str(new_dir)):
            with patch("src.repl._find_context_file", return_value=(ctx_path, "CLAUDE.md")):
                _update_system_prompt_cwd(messages)

        content = messages[0]["content"]
        assert "Project Context (CLAUDE.md)" in content
        assert "# New project" in content

    def test_replaces_context_on_cd(self, tmp_path):
        """Project context is replaced when cd'ing between projects."""
        old_dir = tmp_path / "old"
        old_dir.mkdir()
        (old_dir / "YOYO.md").write_text("# Old YOYO project")

        new_dir = tmp_path / "new"
        new_dir.mkdir()
        (new_dir / "AGENTS.md").write_text("# New AGENTS project")

        system = (
            "You are a coding assistant.\n"
            "Current working directory: /tmp/old\n"
            "\n# Project Context (YOYO.md)\n"
            "# Old YOYO project\n"
        )
        messages = _make_system_msg(system)

        ctx_path = str(new_dir / "AGENTS.md")
        with patch("os.getcwd", return_value=str(new_dir)):
            with patch("src.repl._find_context_file", return_value=(ctx_path, "AGENTS.md")):
                _update_system_prompt_cwd(messages)

        content = messages[0]["content"]
        assert "Project Context (AGENTS.md)" in content
        assert "# New AGENTS project" in content
        assert "Old YOYO project" not in content

    def test_cwd_line_updated(self, tmp_path):
        """CWD line is updated even when no context files change."""
        system = "You are a coding assistant.\nCurrent working directory: /old/path\n"
        messages = _make_system_msg(system)

        with patch("os.getcwd", return_value="/new/path"):
            _update_system_prompt_cwd(messages)

        assert "Current working directory: /new/path" in messages[0]["content"]
        assert "/old/path" not in messages[0]["content"]

    def test_no_system_message(self):
        """Does nothing when messages list has no system message."""
        messages = [{"role": "user", "content": "hello"}]
        _update_system_prompt_cwd(messages)  # should not crash

    def test_empty_content(self):
        """Does nothing when system message has empty content."""
        messages = [{"role": "system", "content": ""}]
        _update_system_prompt_cwd(messages)  # should not crash
