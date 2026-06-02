"""Tests for session save/load preserving usage data."""

import json
import tempfile
from pathlib import Path

from src.repl import _save_session, _load_session
from src.provider import Usage


def test_save_session_includes_usage():
    """Usage data should be saved in the session file."""
    messages = [{"role": "user", "content": "hello"}]
    usage = Usage(input_tokens=100, output_tokens=50)

    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "session.json")
        result = _save_session(path, messages, "glm-5.1", usage=usage)
        assert "[OK]" in result

        # Verify the file contains usage data
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        assert "usage" in data
        assert data["usage"]["input_tokens"] == 100
        assert data["usage"]["output_tokens"] == 50


def test_load_session_restores_usage():
    """Loading a session should restore usage data."""
    messages = [{"role": "user", "content": "hello"}]
    usage = Usage(input_tokens=200, output_tokens=80)

    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "session.json")
        _save_session(path, messages, "glm-5.1", usage=usage)

        result = _load_session(path)
        assert result is not None
        loaded_messages, loaded_model, loaded_usage, warnings = result
        assert loaded_usage is not None
        assert loaded_usage.input_tokens == 200
        assert loaded_usage.output_tokens == 80


def test_load_session_without_usage_defaults_to_zero():
    """Old session files without usage data should default to zero usage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "session.json")
        # Write a session file without usage (old format)
        data = {
            "version": 1,
            "timestamp": "2026-01-01T00:00:00",
            "model": "glm-5.1",
            "messages": [{"role": "user", "content": "hello"}],
        }
        Path(path).write_text(json.dumps(data), encoding="utf-8")

        result = _load_session(path)
        assert result is not None
        _, _, loaded_usage, _ = result
        assert loaded_usage.input_tokens == 0
        assert loaded_usage.output_tokens == 0


def test_load_session_returns_four_tuple():
    """_load_session should now return (messages, model, usage, warnings) tuple."""
    messages = [{"role": "user", "content": "test"}]
    usage = Usage(input_tokens=10, output_tokens=5)

    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "session.json")
        _save_session(path, messages, "glm-5.1", usage=usage)

        result = _load_session(path)
        assert result is not None
        assert len(result) == 4
