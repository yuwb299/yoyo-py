"""Tests for git-aware context in system prompt.

When the user is in a git repo, the system prompt should include
information about recently changed files and the current branch.
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from src.repl import load_system_prompt, _git_context


class TestGitAwareContext:
    """Test that load_system_prompt includes git context when available."""

    def test_git_context_included_in_prompt(self):
        """When in a git repo, system prompt includes branch and recent changes."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="true\n"),               # rev-parse
                MagicMock(returncode=0, stdout="main\n"),               # branch --show-current
                MagicMock(returncode=0, stdout="src/agent.py\nsrc/tools.py\n"),  # diff --name-only
                MagicMock(returncode=0, stdout=""),                      # diff --cached --name-only
                MagicMock(returncode=0, stdout=""),                      # ls-files --others
            ]
            prompt = load_system_prompt()

        assert "main" in prompt
        assert "src/agent.py" in prompt
        assert "src/tools.py" in prompt

    def test_no_git_context_when_not_in_repo(self):
        """When not in a git repo, no git context is included."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=128, stdout="")
            prompt = load_system_prompt()

        # Should still have base system prompt
        assert "coding assistant" in prompt
        # Should NOT have git context section
        assert "Git Context" not in prompt

    def test_git_context_includes_untracked_files(self):
        """Untracked (new) files should also be shown in git context."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="true\n"),       # rev-parse
                MagicMock(returncode=0, stdout="feature\n"),    # branch --show-current
                MagicMock(returncode=0, stdout="src/agent.py\n"),   # diff --name-only
                MagicMock(returncode=0, stdout=""),              # diff --cached --name-only
                MagicMock(returncode=0, stdout="new_feature.py\n"),  # ls-files --others
            ]
            prompt = load_system_prompt()

        assert "new_feature.py" in prompt
        assert "feature" in prompt

    def test_git_context_handles_detached_head(self):
        """When in detached HEAD state, show commit hash instead of branch name."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="true\n"),       # rev-parse
                MagicMock(returncode=1, stdout=""),              # branch --show-current (fails)
                MagicMock(returncode=0, stdout="abc1234\n"),    # rev-parse --short HEAD
                MagicMock(returncode=0, stdout="file.py\n"),    # diff --name-only
                MagicMock(returncode=0, stdout=""),              # diff --cached --name-only
                MagicMock(returncode=0, stdout=""),              # ls-files --others
            ]
            prompt = load_system_prompt()

        assert "abc1234" in prompt

    def test_git_context_function_directly(self):
        """Test _git_context function directly."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="true\n"),
                MagicMock(returncode=0, stdout="main\n"),
                MagicMock(returncode=0, stdout=""),
                MagicMock(returncode=0, stdout=""),
                MagicMock(returncode=0, stdout=""),
            ]
            ctx = _git_context()

        assert "main" in ctx
        assert "Branch: main" in ctx

    def test_git_context_limits_files(self):
        """When there are many changed files, only show the first 20."""
        with patch("subprocess.run") as mock_run:
            many_files = "\n".join(f"file_{i}.py" for i in range(25))
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="true\n"),
                MagicMock(returncode=0, stdout="main\n"),
                MagicMock(returncode=0, stdout=many_files + "\n"),
                MagicMock(returncode=0, stdout=""),
                MagicMock(returncode=0, stdout=""),
            ]
            ctx = _git_context()

        assert "5 more" in ctx
        assert "file_0.py" in ctx
