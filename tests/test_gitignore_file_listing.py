"""Tests for gitignore-aware file listing in list_files and glob tools.

When inside a git repo, list_files should exclude files matched by .gitignore
(__pycache__, *.pyc, node_modules, .git/, build artifacts, etc).
Outside a git repo, it should fall back to showing everything as before.
"""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from src.tools import tool_list_files, tool_glob


@pytest.fixture
def git_ignored_repo(tmp_path):
    """Create a temporary git repo with .gitignored files.

    Structure:
    ├── .gitignore
    ├── src/
    │   ├── main.py
    │   └── __pycache__/
    │       └── main.cpython-311.pyc
    ├── build/
    │   └── output.o
    ├── node_modules/
    │   └── package/...
    ├── README.md
    └── secret.key
    """
    repo = tmp_path / "repo"
    repo.mkdir()

    # Init git repo
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, timeout=10)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo, capture_output=True, timeout=5,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo, capture_output=True, timeout=5,
    )

    # Create .gitignore
    gitignore = repo / ".gitignore"
    gitignore.write_text(
        "__pycache__/\n"
        "*.pyc\n"
        "build/\n"
        "node_modules/\n"
        "*.key\n"
    )

    # Create tracked files
    (repo / "src").mkdir()
    (repo / "src" / "main.py").write_text("print('hello')")
    (repo / "README.md").write_text("# Test")

    # Create gitignored files
    (repo / "src" / "__pycache__").mkdir()
    (repo / "src" / "__pycache__" / "main.cpython-311.pyc").write_bytes(b"\x00")
    (repo / "build").mkdir()
    (repo / "build" / "output.o").write_text("binary")
    (repo / "node_modules").mkdir()
    (repo / "node_modules" / "package").mkdir()
    (repo / "node_modules" / "package" / "index.js").write_text("module.exports = {}")
    (repo / "secret.key").write_text("secret123")

    # Commit so git tracks files
    subprocess.run(["git", "add", "-A"], cwd=repo, capture_output=True, timeout=10)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo, capture_output=True, timeout=10,
    )

    return repo


@pytest.fixture
def non_git_dir(tmp_path):
    """A directory that is NOT a git repo."""
    d = tmp_path / "plain"
    d.mkdir()
    (d / "hello.py").write_text("print('hi')")
    (d / "__pycache__").mkdir()
    (d / "__pycache__" / "hello.cpython-311.pyc").write_bytes(b"\x00")
    return d


class TestListFilesGitignore:
    """Tests for list_files respecting .gitignore in git repos."""

    def test_excludes_pycache(self, git_ignored_repo):
        """__pycache__ directories should be excluded in a git repo."""
        result = tool_list_files(str(git_ignored_repo))
        assert "__pycache__" not in result
        assert ".pyc" not in result

    def test_excludes_build_dir(self, git_ignored_repo):
        """Build directories in .gitignore should be excluded."""
        result = tool_list_files(str(git_ignored_repo))
        assert "build/" not in result
        assert "output.o" not in result

    def test_excludes_node_modules(self, git_ignored_repo):
        """node_modules should be excluded."""
        result = tool_list_files(str(git_ignored_repo))
        # Check that no file INSIDE a node_modules directory is listed.
        # Note: the temp dir path itself may contain "node_modules" in the test name.
        repo_prefix = str(git_ignored_repo)
        for line in result.splitlines():
            line = line.strip()
            if line.startswith("/"):
                # Get the relative path from the repo root
                rel = line.lstrip()
                if rel.startswith(repo_prefix):
                    rel = rel[len(repo_prefix):].lstrip("/").split("  ")[0]
                    parts = rel.split(os.sep)
                    assert "node_modules" not in parts, f"Found node_modules in path: {rel}"

    def test_excludes_ignored_extensions(self, git_ignored_repo):
        """Files with gitignored extensions (e.g. *.key) should be excluded."""
        result = tool_list_files(str(git_ignored_repo))
        assert "secret.key" not in result

    def test_includes_tracked_files(self, git_ignored_repo):
        """Tracked files should still appear."""
        result = tool_list_files(str(git_ignored_repo))
        assert "main.py" in result
        assert "README.md" in result
        assert ".gitignore" in result

    def test_non_git_repo_shows_everything(self, non_git_dir):
        """Outside a git repo, all files should be listed (no filtering)."""
        result = tool_list_files(str(non_git_dir))
        assert "hello.py" in result
        # __pycache__ and .pyc should appear since no gitignore filtering
        assert "__pycache__" in result


class TestGlobGitignore:
    """Tests for glob tool respecting .gitignore in git repos."""

    def test_glob_excludes_pyc(self, git_ignored_repo):
        """glob **/*.py should not include .pyc files in git repos."""
        result = tool_glob("**/*.py", path=str(git_ignored_repo))
        assert ".pyc" not in result
        assert "main.py" in result

    def test_glob_excludes_node_modules(self, git_ignored_repo):
        """glob **/* should not include node_modules contents."""
        result = tool_glob("**/*.js", path=str(git_ignored_repo))
        # node_modules is gitignored, so index.js should not appear
        assert "index.js" not in result

    def test_glob_includes_tracked(self, git_ignored_repo):
        """glob should include tracked files."""
        result = tool_glob("**/*.py", path=str(git_ignored_repo))
        assert "main.py" in result

    def test_glob_md_files(self, git_ignored_repo):
        """glob for .md files should find README.md but not gitignored .md files."""
        result = tool_glob("**/*.md", path=str(git_ignored_repo))
        assert "README.md" in result
