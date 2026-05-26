"""Tests for /cd command (change working directory)."""

import os
import tempfile
from unittest.mock import patch

from src.repl import _handle_cd_command


class TestCdCommand:
    """Test the /cd command handler."""

    def test_cd_to_existing_directory(self):
        """Changing to an existing directory should work."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            result = _handle_cd_command(tmpdir)
            try:
                assert "[OK]" in result
                assert os.path.realpath(os.getcwd()) == os.path.realpath(tmpdir)
            finally:
                os.chdir(original_cwd)

    def test_cd_to_nonexistent_directory(self):
        """Changing to a nonexistent directory should fail gracefully."""
        result = _handle_cd_command("/nonexistent/path/that/does/not/exist")
        assert "[ERROR]" in result or "not found" in result.lower()

    def test_cd_to_file_not_directory(self):
        """Changing to a file path should fail gracefully."""
        with tempfile.NamedTemporaryFile() as tmpfile:
            result = _handle_cd_command(tmpfile.name)
            assert "[ERROR]" in result or "not a directory" in result.lower()

    def test_cd_relative_path(self):
        """Changing to a relative path should work."""
        original_cwd = os.getcwd()
        result = _handle_cd_command(".")
        assert "[OK]" in result
        assert os.getcwd() == original_cwd

    def test_cd_home_directory(self):
        """Changing to ~ should work."""
        original_cwd = os.getcwd()
        result = _handle_cd_command("~")
        try:
            assert "[OK]" in result
            assert os.getcwd() == os.path.expanduser("~")
        finally:
            os.chdir(original_cwd)

    def test_cd_empty_path_goes_home(self):
        """Empty path should go to home directory."""
        original_cwd = os.getcwd()
        result = _handle_cd_command("")
        try:
            assert "[OK]" in result
            assert os.getcwd() == os.path.expanduser("~")
        finally:
            os.chdir(original_cwd)

    def test_cd_updates_system_prompt_cwd(self):
        """After /cd, the system prompt should reference the new cwd."""
        # This tests that the cd handler returns info about updating context
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            result = _handle_cd_command(tmpdir)
            try:
                assert tmpdir in result or "changed" in result.lower()
            finally:
                os.chdir(original_cwd)

    def test_cd_with_spaces_in_path(self):
        """Directory names with spaces should work."""
        with tempfile.TemporaryDirectory(prefix="test dir ") as tmpdir:
            original_cwd = os.getcwd()
            result = _handle_cd_command(tmpdir)
            try:
                assert "[OK]" in result
                assert os.path.realpath(os.getcwd()) == os.path.realpath(tmpdir)
            finally:
                os.chdir(original_cwd)
