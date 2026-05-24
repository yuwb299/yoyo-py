"""Tests for project memory system (/remember, /memories, /forget)."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.repl import _add_memory, _list_memories, _forget_memory, _load_memories_into_prompt


@pytest.fixture
def memory_dir(tmp_path):
    """Create a temporary .yoyo directory for memory tests."""
    yoyo_dir = tmp_path / ".yoyo"
    yoyo_dir.mkdir()
    return yoyo_dir


@pytest.fixture
def memory_file(memory_dir):
    """Return the path to the memories file."""
    return memory_dir / "memories.json"


class TestAddMemory:
    def test_add_memory_creates_file(self, memory_dir, memory_file):
        result = _add_memory("Use pytest for testing", memory_dir)
        assert memory_file.exists()
        data = json.loads(memory_file.read_text())
        assert len(data) == 1
        assert data[0]["text"] == "Use pytest for testing"
        assert "id" in data[0]
        assert "timestamp" in data[0]

    def test_add_memory_returns_confirmation(self, memory_dir):
        result = _add_memory("Use pytest for testing", memory_dir)
        assert "[OK]" in result
        assert "Remembered" in result

    def test_add_memory_appends_to_existing(self, memory_dir, memory_file):
        _add_memory("First memory", memory_dir)
        _add_memory("Second memory", memory_dir)
        data = json.loads(memory_file.read_text())
        assert len(data) == 2
        assert data[0]["text"] == "First memory"
        assert data[1]["text"] == "Second memory"

    def test_add_memory_empty_text_rejected(self, memory_dir):
        result = _add_memory("  ", memory_dir)
        assert "[ERROR]" in result
        assert "empty" in result.lower()

    def test_add_memory_creates_directory(self, tmp_path):
        new_dir = tmp_path / "new_yoyo"
        result = _add_memory("Test", new_dir)
        assert (new_dir / "memories.json").exists()

    def test_add_memory_includes_id(self, memory_dir, memory_file):
        _add_memory("Memory 1", memory_dir)
        _add_memory("Memory 2", memory_dir)
        data = json.loads(memory_file.read_text())
        ids = [m["id"] for m in data]
        assert len(set(ids)) == 2  # IDs are unique


class TestListMemories:
    def test_list_empty(self, memory_dir):
        result = _list_memories(memory_dir)
        assert "No memories" in result

    def test_list_memories(self, memory_dir):
        _add_memory("First memory", memory_dir)
        _add_memory("Second memory", memory_dir)
        result = _list_memories(memory_dir)
        assert "First memory" in result
        assert "Second memory" in result

    def test_list_memories_with_ids(self, memory_dir, memory_file):
        _add_memory("Test memory", memory_dir)
        data = json.loads(memory_file.read_text())
        mem_id = data[0]["id"]
        result = _list_memories(memory_dir)
        assert str(mem_id) in result

    def test_list_memories_no_file(self, memory_dir):
        result = _list_memories(memory_dir)
        assert "No memories" in result


class TestForgetMemory:
    def test_forget_by_id(self, memory_dir, memory_file):
        _add_memory("Keep this", memory_dir)
        _add_memory("Forget this", memory_dir)
        data = json.loads(memory_file.read_text())
        forget_id = data[1]["id"]

        result = _forget_memory(forget_id, memory_dir)
        assert "[OK]" in result

        data = json.loads(memory_file.read_text())
        assert len(data) == 1
        assert data[0]["text"] == "Keep this"

    def test_forget_nonexistent_id(self, memory_dir, memory_file):
        _add_memory("Test", memory_dir)
        result = _forget_memory(999, memory_dir)
        assert "[ERROR]" in result or "not found" in result.lower()

    def test_forget_no_memories_file(self, memory_dir):
        result = _forget_memory(1, memory_dir)
        assert "not found" in result.lower() or "no memories" in result.lower()

    def test_forget_last_memory_removes_file(self, memory_dir, memory_file):
        _add_memory("Only memory", memory_dir)
        data = json.loads(memory_file.read_text())
        result = _forget_memory(data[0]["id"], memory_dir)
        # File should be removed or empty
        if memory_file.exists():
            data = json.loads(memory_file.read_text())
            assert len(data) == 0


class TestLoadMemoriesIntoPrompt:
    def test_load_memories_no_file(self, memory_dir):
        result = _load_memories_into_prompt(memory_dir)
        assert result == ""

    def test_load_memories_with_data(self, memory_dir):
        _add_memory("Always use type hints", memory_dir)
        _add_memory("Run pytest before committing", memory_dir)
        result = _load_memories_into_prompt(memory_dir)
        assert "type hints" in result
        assert "pytest" in result
        assert "Project Memories" in result

    def test_load_memories_format(self, memory_dir):
        _add_memory("Test memory text", memory_dir)
        result = _load_memories_into_prompt(memory_dir)
        assert "Test memory text" in result
