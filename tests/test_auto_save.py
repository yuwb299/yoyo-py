"""Tests for session auto-save on exit."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.repl import _auto_save_session
from src.provider import Usage


class TestAutoSaveSession:
    """Test the auto-save session function."""

    def test_auto_save_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            messages = [
                {"role": "system", "content": "test"},
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi"},
            ]
            save_path = os.path.join(tmpdir, ".yoyo", "autosave.json")

            result = _auto_save_session(
                save_path=save_path,
                messages=messages,
                model="glm-5.1",
                usage=Usage(input_tokens=10, output_tokens=5),
            )

            assert result.startswith("[OK]")
            assert os.path.exists(save_path)

            # Verify content
            data = json.loads(Path(save_path).read_text())
            assert data["model"] == "glm-5.1"
            assert len(data["messages"]) == 3
            assert data["autosaved"] is True
            assert data["usage"]["input_tokens"] == 10

    def test_auto_save_with_empty_messages(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = os.path.join(tmpdir, ".yoyo", "autosave.json")

            result = _auto_save_session(
                save_path=save_path,
                messages=[],
                model="glm-5.1",
                usage=Usage(),
            )

            # Should not save empty conversations
            assert "skipped" in result.lower() or not os.path.exists(save_path)

    def test_auto_save_with_only_system_prompt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = os.path.join(tmpdir, ".yoyo", "autosave.json")
            messages = [{"role": "system", "content": "test"}]

            result = _auto_save_session(
                save_path=save_path,
                messages=messages,
                model="glm-5.1",
                usage=Usage(),
            )

            # System-only conversations are not worth saving
            assert "skipped" in result.lower() or not os.path.exists(save_path)

    def test_auto_save_handles_error_gracefully(self):
        result = _auto_save_session(
            save_path="/nonexistent/path/deep/autosave.json",
            messages=[{"role": "user", "content": "test"}],
            model="glm-5.1",
            usage=Usage(),
        )

        # Should not crash, just report error
        assert "ERROR" in result or "skipped" in result.lower()

    def test_auto_save_creates_parent_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = os.path.join(tmpdir, "deep", "nested", "autosave.json")

            result = _auto_save_session(
                save_path=save_path,
                messages=[
                    {"role": "user", "content": "hello"},
                ],
                model="glm-5.1",
                usage=Usage(),
            )

            assert os.path.exists(save_path)

    def test_auto_save_overwrites_existing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = os.path.join(tmpdir, "autosave.json")

            # First save
            _auto_save_session(
                save_path=save_path,
                messages=[{"role": "user", "content": "first"}],
                model="glm-5.1",
                usage=Usage(),
            )

            # Second save should overwrite
            _auto_save_session(
                save_path=save_path,
                messages=[{"role": "user", "content": "second"}],
                model="glm-5.1",
                usage=Usage(),
            )

            data = json.loads(Path(save_path).read_text())
            assert data["messages"][0]["content"] == "second"
