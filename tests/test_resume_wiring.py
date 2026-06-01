"""Tests for --resume CLI flag wiring: main.py passes it to run_repl, and
run_repl restores the autosaved session before starting the REPL loop."""

import json
import os
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.repl import _handle_resume_command, run_repl


def _collect_events(coro):
    """Helper to run async coroutine synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


class TestResumeWiringInMain:
    """Verify --resume flag is parsed and passed through to run_repl."""

    def test_parse_args_resume_flag(self):
        from src.main import parse_args
        with patch("sys.argv", ["prog", "--resume"]):
            args = parse_args()
        assert args.resume is True

    def test_parse_args_no_resume_default(self):
        from src.main import parse_args
        with patch("sys.argv", ["prog"]):
            args = parse_args()
        assert args.resume is False


class TestResumeInRunRepl:
    """Verify run_repl handles resume=True by restoring the autosaved session."""

    def test_run_repl_with_resume_restores_session(self, tmp_path, monkeypatch):
        """When resume=True and autosave exists, run_repl restores the session."""
        monkeypatch.chdir(tmp_path)

        # Create autosave file
        yoyo_dir = tmp_path / ".yoyo"
        yoyo_dir.mkdir()
        autosave = yoyo_dir / "autosave.json"
        data = {
            "autosaved": True,
            "messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi there"},
            ],
            "model": "glm-5.1",
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }
        autosave.write_text(json.dumps(data), encoding="utf-8")

        # Create a mock provider
        mock_provider = MagicMock()
        mock_provider.model = "glm-5.1"
        mock_provider.base_url = "https://example.com"
        mock_provider.api_key = "test-key"
        mock_provider.max_tokens = None
        mock_provider.temperature = None
        mock_provider.top_p = None

        # Mock _read_multiline_input to immediately exit
        with patch("src.repl._read_multiline_input", side_effect=EOFError):
            with patch("src.repl._auto_save_on_exit"):
                _collect_events(run_repl(
                    provider=mock_provider,
                    resume=True,
                ))

        # The autosave file should be consumed
        assert not autosave.exists()

    def test_run_repl_with_resume_no_autosave(self, tmp_path, monkeypatch, capsys):
        """When resume=True but no autosave exists, run_repl starts fresh."""
        monkeypatch.chdir(tmp_path)

        mock_provider = MagicMock()
        mock_provider.model = "glm-5.1"
        mock_provider.base_url = "https://example.com"
        mock_provider.api_key = "test-key"
        mock_provider.max_tokens = None
        mock_provider.temperature = None
        mock_provider.top_p = None

        with patch("src.repl._read_multiline_input", side_effect=EOFError):
            with patch("src.repl._auto_save_on_exit"):
                _collect_events(run_repl(
                    provider=mock_provider,
                    resume=True,
                ))

        captured = capsys.readouterr()
        # Should not crash — just start normally
        assert "yoyo-py" in captured.out

    def test_run_repl_resume_shows_restored_message(self, tmp_path, monkeypatch, capsys):
        """When resume restores a session, it shows a confirmation message."""
        monkeypatch.chdir(tmp_path)

        yoyo_dir = tmp_path / ".yoyo"
        yoyo_dir.mkdir()
        autosave = yoyo_dir / "autosave.json"
        data = {
            "autosaved": True,
            "messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi there"},
            ],
            "model": "glm-5.1",
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }
        autosave.write_text(json.dumps(data), encoding="utf-8")

        mock_provider = MagicMock()
        mock_provider.model = "glm-5.1"
        mock_provider.base_url = "https://example.com"
        mock_provider.api_key = "test-key"
        mock_provider.max_tokens = None
        mock_provider.temperature = None
        mock_provider.top_p = None

        with patch("src.repl._read_multiline_input", side_effect=EOFError):
            with patch("src.repl._auto_save_on_exit"):
                _collect_events(run_repl(
                    provider=mock_provider,
                    resume=True,
                ))

        captured = capsys.readouterr()
        assert "Resumed session" in captured.out
        assert "2 messages" in captured.out

    def test_run_repl_resume_ignored_for_pipe_input(self, tmp_path, monkeypatch, capsys):
        """resume=True is ignored when pipe_input is provided."""
        monkeypatch.chdir(tmp_path)

        # Create autosave — it should NOT be consumed since pipe_input takes precedence
        yoyo_dir = tmp_path / ".yoyo"
        yoyo_dir.mkdir()
        autosave = yoyo_dir / "autosave.json"
        data = {
            "autosaved": True,
            "messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "hello"},
            ],
            "model": "glm-5.1",
        }
        autosave.write_text(json.dumps(data), encoding="utf-8")

        mock_provider = MagicMock()
        mock_provider.model = "glm-5.1"
        mock_provider.base_url = "https://example.com"
        mock_provider.api_key = "test-key"
        mock_provider.max_tokens = None
        mock_provider.temperature = None
        mock_provider.top_p = None

        with patch("src.repl._run_agent_turn", new_callable=AsyncMock):
            _collect_events(run_repl(
                provider=mock_provider,
                pipe_input="do something",
                resume=True,
            ))

        # Autosave should still exist — resume was skipped because pipe_input
        assert autosave.exists()

    def test_run_repl_resume_ignored_for_initial_prompt(self, tmp_path, monkeypatch, capsys):
        """resume=True is ignored when initial_prompt is provided."""
        monkeypatch.chdir(tmp_path)

        yoyo_dir = tmp_path / ".yoyo"
        yoyo_dir.mkdir()
        autosave = yoyo_dir / "autosave.json"
        data = {
            "autosaved": True,
            "messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "hello"},
            ],
            "model": "glm-5.1",
        }
        autosave.write_text(json.dumps(data), encoding="utf-8")

        mock_provider = MagicMock()
        mock_provider.model = "glm-5.1"
        mock_provider.base_url = "https://example.com"
        mock_provider.api_key = "test-key"
        mock_provider.max_tokens = None
        mock_provider.temperature = None
        mock_provider.top_p = None

        with patch("src.repl._run_agent_turn", new_callable=AsyncMock):
            _collect_events(run_repl(
                provider=mock_provider,
                initial_prompt="do something",
                resume=True,
            ))

        # Autosave should still exist — resume was skipped because initial_prompt
        assert autosave.exists()
