"""Tests for /resume command — auto-detect and reload last auto-saved session."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from src.repl import _handle_resume_command, _auto_save_session


class TestHandleResumeCommand:
    """Tests for _handle_resume_command — the core logic of /resume."""

    def test_no_autosave_file(self):
        """When no autosave exists, return a message saying so."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _handle_resume_command(cwd=tmpdir)
            assert "No auto-saved session found" in result

    def test_empty_autosave_no_real_messages(self):
        """Autosave with only system prompt should be treated as empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            autosave_path = os.path.join(tmpdir, ".yoyo", "autosave.json")
            os.makedirs(os.path.dirname(autosave_path))
            data = {
                "version": 1,
                "model": "test-model",
                "messages": [
                    {"role": "system", "content": "You are a helper."},
                ],
                "autosaved": True,
            }
            Path(autosave_path).write_text(json.dumps(data), encoding="utf-8")

            result = _handle_resume_command(cwd=tmpdir)
            assert "No auto-saved session found" in result

    def test_valid_autosave_returns_session_data(self):
        """Valid autosave with real messages should return (messages, model, usage)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            autosave_path = os.path.join(tmpdir, ".yoyo", "autosave.json")
            os.makedirs(os.path.dirname(autosave_path))
            data = {
                "version": 1,
                "model": "test-model",
                "messages": [
                    {"role": "system", "content": "You are a helper."},
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi there!"},
                ],
                "autosaved": True,
                "usage": {"input_tokens": 100, "output_tokens": 50},
            }
            Path(autosave_path).write_text(json.dumps(data), encoding="utf-8")

            result = _handle_resume_command(cwd=tmpdir)
            # Should return a tuple of (messages, model, usage) for valid autosave
            assert isinstance(result, tuple)
            messages, model, usage = result
            assert model == "test-model"
            assert len(messages) == 3
            assert messages[1]["content"] == "Hello"
            assert usage.input_tokens == 100
            assert usage.output_tokens == 50

    def test_valid_autosave_no_usage(self):
        """Autosave without usage data should return zero usage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            autosave_path = os.path.join(tmpdir, ".yoyo", "autosave.json")
            os.makedirs(os.path.dirname(autosave_path))
            data = {
                "version": 1,
                "model": "test-model",
                "messages": [
                    {"role": "system", "content": "You are a helper."},
                    {"role": "user", "content": "Hello"},
                ],
                "autosaved": True,
            }
            Path(autosave_path).write_text(json.dumps(data), encoding="utf-8")

            result = _handle_resume_command(cwd=tmpdir)
            assert isinstance(result, tuple)
            messages, model, usage = result
            assert usage.input_tokens == 0
            assert usage.output_tokens == 0

    def test_invalid_json_autosave(self):
        """Corrupted autosave file should return an error message."""
        with tempfile.TemporaryDirectory() as tmpdir:
            autosave_path = os.path.join(tmpdir, ".yoyo", "autosave.json")
            os.makedirs(os.path.dirname(autosave_path))
            Path(autosave_path).write_text("{invalid json", encoding="utf-8")

            result = _handle_resume_command(cwd=tmpdir)
            # Should return a string error message
            assert isinstance(result, str)
            assert "error" in result.lower() or "failed" in result.lower()

    def test_non_autosave_session_file_ignored(self):
        """Regular saved session (not autosaved) should not be picked up by /resume."""
        with tempfile.TemporaryDirectory() as tmpdir:
            autosave_path = os.path.join(tmpdir, ".yoyo", "autosave.json")
            os.makedirs(os.path.dirname(autosave_path))
            data = {
                "version": 1,
                "model": "test-model",
                "messages": [
                    {"role": "system", "content": "You are a helper."},
                    {"role": "user", "content": "Hello"},
                ],
                # No "autosaved": True — this is a manual save
            }
            Path(autosave_path).write_text(json.dumps(data), encoding="utf-8")

            result = _handle_resume_command(cwd=tmpdir)
            assert "No auto-saved session found" in result

    def test_deletes_autosave_after_resume(self):
        """After successful resume, the autosave file should be cleaned up."""
        with tempfile.TemporaryDirectory() as tmpdir:
            autosave_path = os.path.join(tmpdir, ".yoyo", "autosave.json")
            os.makedirs(os.path.dirname(autosave_path))
            data = {
                "version": 1,
                "model": "test-model",
                "messages": [
                    {"role": "system", "content": "You are a helper."},
                    {"role": "user", "content": "Hello"},
                ],
                "autosaved": True,
            }
            Path(autosave_path).write_text(json.dumps(data), encoding="utf-8")

            result = _handle_resume_command(cwd=tmpdir)
            assert isinstance(result, tuple)
            # Autosave should be deleted after successful resume
            assert not Path(autosave_path).exists()


class TestResumeSummary:
    """Tests for the resume summary message formatting."""

    def test_summary_format(self):
        """Resume result should include message count and model info."""
        with tempfile.TemporaryDirectory() as tmpdir:
            autosave_path = os.path.join(tmpdir, ".yoyo", "autosave.json")
            os.makedirs(os.path.dirname(autosave_path))
            data = {
                "version": 1,
                "model": "glm-5.1",
                "messages": [
                    {"role": "system", "content": "You are a helper."},
                    {"role": "user", "content": "Write tests"},
                    {"role": "assistant", "content": "Done"},
                ],
                "autosaved": True,
                "usage": {"input_tokens": 500, "output_tokens": 200},
            }
            Path(autosave_path).write_text(json.dumps(data), encoding="utf-8")

            result = _handle_resume_command(cwd=tmpdir)
            assert isinstance(result, tuple)
            messages, model, usage = result
            # Verify the data is correct
            assert len(messages) == 3
            assert model == "glm-5.1"
            assert usage.input_tokens == 500
