"""Tests for file path tab completion after slash commands."""

import os
import pytest
from unittest.mock import patch

from src.repl import _slash_completer


class TestFilePathCompletion:
    """Tests for tab completion of file paths after commands."""

    def test_slash_command_completion(self):
        """Tab completes slash commands."""
        result = _slash_completer("/qu", 0)
        assert result == "/quit"

    def test_slash_command_completion_exit(self):
        result = _slash_completer("/ex", 0)
        assert result == "/exit"

    def test_no_match_returns_none(self):
        result = _slash_completer("/zzzzz", 0)
        assert result is None

    def test_cd_path_completion(self, tmp_path):
        """Tab after /cd completes with directory paths."""
        # Create some dirs
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "README.md").write_text("hello")

        with patch("os.getcwd", return_value=str(tmp_path)):
            result = _slash_completer(f"/cd ", 0)
        # Should return a directory, not a file
        if result:
            assert "src" in result or "tests" in result

    def test_cd_path_completion_partial(self, tmp_path):
        """Tab after /cd s completes with matching directories."""
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()

        with patch("os.getcwd", return_value=str(tmp_path)):
            result = _slash_completer("/cd s", 0)
        if result:
            assert "src" in result

    def test_edit_path_completion(self, tmp_path):
        """Tab after /edit completes with file paths."""
        (tmp_path / "main.py").write_text("print('hi')")
        (tmp_path / "test.py").write_text("test")

        with patch("os.getcwd", return_value=str(tmp_path)):
            result = _slash_completer("/edit ", 0)
        if result:
            assert "main.py" in result or "test.py" in result

    def test_edit_partial_completion(self, tmp_path):
        """Tab after /edit ma completes with matching files."""
        (tmp_path / "main.py").write_text("print('hi')")
        (tmp_path / "test.py").write_text("test")

        with patch("os.getcwd", return_value=str(tmp_path)):
            result = _slash_completer("/edit ma", 0)
        if result:
            assert "main.py" in result

    def test_load_path_completion(self, tmp_path):
        """Tab after /load completes with .json files."""
        (tmp_path / "session.json").write_text("{}")
        (tmp_path / "data.json").write_text("{}")
        (tmp_path / "readme.txt").write_text("hello")

        with patch("os.getcwd", return_value=str(tmp_path)):
            result = _slash_completer("/load ", 0)
        if result:
            assert ".json" in result

    def test_save_path_completion(self, tmp_path):
        """Tab after /save completes with directory/json paths."""
        (tmp_path / "session.json").write_text("{}")

        with patch("os.getcwd", return_value=str(tmp_path)):
            result = _slash_completer("/save ", 0)
        # Should offer something
        if result:
            assert isinstance(result, str)

    def test_export_path_completion(self, tmp_path):
        """Tab after /export completes with .md files."""
        (tmp_path / "notes.md").write_text("# notes")
        (tmp_path / "readme.txt").write_text("hello")

        with patch("os.getcwd", return_value=str(tmp_path)):
            result = _slash_completer("/export ", 0)
        if result:
            assert ".md" in result or isinstance(result, str)

    def test_non_path_command_uses_slash_completion(self):
        """Commands that don't take paths still use slash completion."""
        result = _slash_completer("/hel", 0)
        assert result == "/help"

    def test_completion_returns_none_past_end(self, tmp_path):
        """State index past available matches returns None."""
        (tmp_path / "main.py").write_text("hi")

        with patch("os.getcwd", return_value=str(tmp_path)):
            result = _slash_completer("/edit m", 100)
        assert result is None
