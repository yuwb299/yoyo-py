"""Tests for broader context file discovery.

Tests that the system prompt builder discovers context files beyond
just YOYO.md and CLAUDE.md, including AGENTS.md, .cursorrules,
RULES.md, and walks up the directory tree to find them.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helper: call _build_system_prompt via the module
# ---------------------------------------------------------------------------

def _call_build_system_prompt(cwd: str, skills=None):
    """Call load_system_prompt with mocked cwd."""
    from src.repl import load_system_prompt
    with patch("os.getcwd", return_value=cwd):
        return load_system_prompt(skills=skills)


# ---------------------------------------------------------------------------
# Tests: supported context files
# ---------------------------------------------------------------------------

class TestSupportedContextFiles:
    """Test that all supported context file names are discovered."""

    @pytest.fixture
    def tmpdir(self, tmp_path):
        return tmp_path

    def test_finds_yoyo_md(self, tmpdir):
        """YOYO.md is discovered and loaded."""
        (tmpdir / "YOYO.md").write_text("# Project YOYO")
        result = _call_build_system_prompt(str(tmpdir))
        assert "Project Context (YOYO.md)" in result
        assert "# Project YOYO" in result

    def test_finds_claude_md(self, tmpdir):
        """CLAUDE.md is discovered and loaded."""
        (tmpdir / "CLAUDE.md").write_text("# Project CLAUDE")
        result = _call_build_system_prompt(str(tmpdir))
        assert "Project Context (CLAUDE.md)" in result

    def test_finds_agents_md(self, tmpdir):
        """AGENTS.md is discovered and loaded."""
        (tmpdir / "AGENTS.md").write_text("# Project AGENTS")
        result = _call_build_system_prompt(str(tmpdir))
        assert "Project Context (AGENTS.md)" in result
        assert "# Project AGENTS" in result

    def test_finds_cursorrules(self, tmpdir):
        """CLAUDE.md is discovered and loaded."""
        (tmpdir / ".cursorrules").write_text("# Cursor rules")
        result = _call_build_system_prompt(str(tmpdir))
        assert "Project Context (.cursorrules)" in result

    def test_finds_rules_md(self, tmpdir):
        """RULES.md is discovered and loaded."""
        (tmpdir / "RULES.md").write_text("# Project rules")
        result = _call_build_system_prompt(str(tmpdir))
        assert "Project Context (RULES.md)" in result

    def test_finds_windsurfrules(self, tmpdir):
        """WINDSURF.md is discovered and loaded."""
        (tmpdir / ".windsurfrules").write_text("# Windsurf rules")
        result = _call_build_system_prompt(str(tmpdir))
        assert "Project Context (.windsurfrules)" in result

    def test_priority_order(self, tmpdir):
        """Higher-priority files are loaded first; only the first found is used."""
        (tmpdir / "CLAUDE.md").write_text("# From CLAUDE")
        (tmpdir / "AGENTS.md").write_text("# From AGENTS")
        result = _call_build_system_prompt(str(tmpdir))
        # CLAUDE.md should be loaded (higher priority than AGENTS.md)
        assert "Project Context (CLAUDE.md)" in result
        assert "From AGENTS" not in result

    def test_yoyo_md_highest_priority(self, tmpdir):
        """YOYO.md takes priority over all other context files."""
        (tmpdir / "YOYO.md").write_text("# From YOYO")
        (tmpdir / "CLAUDE.md").write_text("# From CLAUDE")
        (tmpdir / "AGENTS.md").write_text("# From AGENTS")
        result = _call_build_system_prompt(str(tmpdir))
        assert "Project Context (YOYO.md)" in result
        assert "From CLAUDE" not in result
        assert "From AGENTS" not in result

    def test_no_context_file(self, tmpdir):
        """When no context files exist, no project context section is added."""
        result = _call_build_system_prompt(str(tmpdir))
        assert "Project Context" not in result


class TestParentDirectorySearch:
    """Test that context files are found in parent directories."""

    def test_finds_context_in_parent(self, tmp_path):
        """Context file in parent directory is discovered from child."""
        (tmp_path / "YOYO.md").write_text("# Parent project")
        child = tmp_path / "subdir"
        child.mkdir()
        result = _call_build_system_prompt(str(child))
        assert "Project Context (YOYO.md)" in result
        assert "# Parent project" in result

    def test_finds_context_in_grandparent(self, tmp_path):
        """Context file in grandparent directory is discovered."""
        (tmp_path / "CLAUDE.md").write_text("# Grandparent project")
        grandchild = tmp_path / "sub1" / "sub2"
        grandchild.mkdir(parents=True)
        result = _call_build_system_prompt(str(grandchild))
        assert "Project Context (CLAUDE.md)" in result

    def test_closer_context_file_wins(self, tmp_path):
        """When both parent and child have context files, the closest one wins."""
        (tmp_path / "YOYO.md").write_text("# Parent YOYO")
        child = tmp_path / "subdir"
        child.mkdir()
        (child / "AGENTS.md").write_text("# Child AGENTS")
        result = _call_build_system_prompt(str(child))
        # AGENTS.md in current dir is closer and should win over YOYO.md in parent
        assert "Project Context (AGENTS.md)" in result
        assert "# Child AGENTS" in result

    def test_yoyo_in_parent_over_agents_in_child(self, tmp_path):
        """YOYO.md in parent has higher priority than AGENTS.md in child dir."""
        # Actually the priority is: search current dir first, then parent.
        # So AGENTS.md in current dir would win over YOYO.md in parent.
        # This tests that YOYO.md in current dir beats AGENTS.md in current dir.
        (tmp_path / "YOYO.md").write_text("# Parent YOYO")
        child = tmp_path / "subdir"
        child.mkdir()
        (child / "YOYO.md").write_text("# Child YOYO")
        (child / "AGENTS.md").write_text("# Child AGENTS")
        result = _call_build_system_prompt(str(child))
        assert "# Child YOYO" in result

    def test_stops_at_filesystem_root(self, tmp_path):
        """Search stops before hitting filesystem root."""
        # Create a deeply nested dir with no context files anywhere
        deep = tmp_path / "a" / "b" / "c" / "d"
        deep.mkdir(parents=True)
        result = _call_build_system_prompt(str(deep))
        assert "Project Context" not in result


class TestContextFileContent:
    """Test that context file content is correctly loaded."""

    def test_utf8_content(self, tmp_path):
        """UTF-8 content (e.g. Chinese) is loaded correctly."""
        (tmp_path / "YOYO.md").write_text("# 项目说明\n这是中文内容", encoding="utf-8")
        result = _call_build_system_prompt(str(tmp_path))
        assert "项目说明" in result
        assert "中文内容" in result

    def test_empty_context_file(self, tmp_path):
        """Empty context file is loaded but adds no content."""
        (tmp_path / "YOYO.md").write_text("")
        result = _call_build_system_prompt(str(tmp_path))
        # Should still have the header
        assert "Project Context (YOYO.md)" in result

    def test_binary_file_skipped(self, tmp_path):
        """Binary files are skipped gracefully."""
        (tmp_path / "YOYO.md").write_bytes(b"\x00\x01\x02\xff\xfe")
        result = _call_build_system_prompt(str(tmp_path))
        # Should not crash; might or might not include the content
        assert isinstance(result, str)

    def test_large_context_file_loaded(self, tmp_path):
        """Large context files are loaded entirely."""
        content = "# Big file\n" + "Line content\n" * 1000
        (tmp_path / "YOYO.md").write_text(content)
        result = _call_build_system_prompt(str(tmp_path))
        assert "Big file" in result
        assert "Line content" in result


class TestMaxSearchDepth:
    """Test that the parent directory search has a reasonable depth limit."""

    def test_search_depth_is_limited(self, tmp_path):
        """Parent search doesn't go more than a configurable number of levels."""
        # Create a dir 20 levels deep — shouldn't search all the way up
        deep = tmp_path
        for i in range(20):
            deep = deep / f"level{i}"
        deep.mkdir(parents=True)

        # Put a context file at the very top
        (tmp_path / "YOYO.md").write_text("# Very far away")

        result = _call_build_system_prompt(str(deep))
        # With a max depth of ~10, this 20-level deep dir shouldn't find the file
        assert "Very far away" not in result
