"""Tests for /init command."""

import os
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.repl import _run_init_command


class TestInitCommand:
    """Tests for the /init command that generates YOYO.md."""

    def test_creates_yoyo_md(self, tmp_path):
        """Should create a YOYO.md file."""
        # Create a minimal project structure
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("print('hello')")

        result = _run_init_command(workdir=str(tmp_path))
        assert (tmp_path / "YOYO.md").exists()
        assert "[OK]" in result

    def test_yoyo_md_contains_project_info(self, tmp_path):
        """YOYO.md should contain basic project information."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'my-project'\nversion = '1.0'\n")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text("# main app")

        _run_init_command(workdir=str(tmp_path))
        content = (tmp_path / "YOYO.md").read_text()
        assert "my-project" in content

    def test_yoyo_md_not_overwritten(self, tmp_path):
        """Should not overwrite existing YOYO.md."""
        (tmp_path / "YOYO.md").write_text("# Custom context\nKeep this")
        result = _run_init_command(workdir=str(tmp_path))
        assert "already exists" in result.lower()
        # Content should be unchanged
        assert "Keep this" in (tmp_path / "YOYO.md").read_text()

    def test_yoyo_md_force_overwrite(self, tmp_path):
        """Should overwrite with --force flag."""
        (tmp_path / "YOYO.md").write_text("# Old content")
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")

        result = _run_init_command(workdir=str(tmp_path), force=True)
        assert (tmp_path / "YOYO.md").exists()
        assert "[OK]" in result

    def test_no_project_files(self, tmp_path):
        """Should still generate a basic YOYO.md for empty dirs."""
        result = _run_init_command(workdir=str(tmp_path))
        # Should create a basic YOYO.md even without project files
        assert (tmp_path / "YOYO.md").exists()

    def test_includes_directory_structure(self, tmp_path):
        """YOYO.md should include a directory tree."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("print('hello')")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_main.py").write_text("def test_it(): pass")

        _run_init_command(workdir=str(tmp_path))
        content = (tmp_path / "YOYO.md").read_text()
        assert "src" in content or "structure" in content.lower()

    def test_node_project(self, tmp_path):
        """Should detect Node.js project and include info."""
        (tmp_path / "package.json").write_text('{"name": "my-app", "scripts": {"test": "jest"}}')

        _run_init_command(workdir=str(tmp_path))
        content = (tmp_path / "YOYO.md").read_text()
        assert "my-app" in content or "Node" in content
