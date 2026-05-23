"""Tests for system prompt construction.

Verifies that load_system_prompt includes all expected components:
base instructions, current working directory, git context, etc.
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from src.repl import load_system_prompt


class TestSystemPromptBaseContent:
    """Test that the system prompt always includes base instructions."""

    def test_includes_coding_assistant(self):
        prompt = load_system_prompt()
        assert "coding assistant" in prompt

    def test_includes_cwd(self):
        """System prompt should tell the agent its current working directory."""
        prompt = load_system_prompt()
        assert "Current working directory:" in prompt
        assert os.getcwd() in prompt

    def test_includes_tool_usage_instruction(self):
        prompt = load_system_prompt()
        assert "Use tools proactively" in prompt


class TestSystemPromptWithContextFile:
    """Test that YOYO.md / CLAUDE.md project context is loaded."""

    def test_loads_yoyo_md(self, tmp_path):
        """When YOYO.md exists in cwd, its content is in the system prompt."""
        yoyo = tmp_path / "YOYO.md"
        yoyo.write_text("# Test Project\nThis is a test project.")
        with patch("os.getcwd", return_value=str(tmp_path)):
            prompt = load_system_prompt()
        assert "Test Project" in prompt
        assert "YOYO.md" in prompt

    def test_prefers_yoyo_over_claude(self, tmp_path):
        """YOYO.md takes priority over CLAUDE.md if both exist."""
        (tmp_path / "YOYO.md").write_text("YOYO content")
        (tmp_path / "CLAUDE.md").write_text("CLAUDE content")
        with patch("os.getcwd", return_value=str(tmp_path)):
            prompt = load_system_prompt()
        assert "YOYO content" in prompt
        assert "CLAUDE content" not in prompt

    def test_falls_back_to_claude_md(self, tmp_path):
        """When YOYO.md doesn't exist, CLAUDE.md is used."""
        (tmp_path / "CLAUDE.md").write_text("CLAUDE content")
        with patch("os.getcwd", return_value=str(tmp_path)):
            prompt = load_system_prompt()
        assert "CLAUDE content" in prompt
        assert "CLAUDE.md" in prompt

    def test_no_context_file_ok(self, tmp_path):
        """When neither file exists, the prompt still works."""
        with patch("os.getcwd", return_value=str(tmp_path)):
            prompt = load_system_prompt()
        assert "coding assistant" in prompt
        assert "Project Context" not in prompt
