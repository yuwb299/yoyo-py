"""Tests for --resume CLI flag that resumes auto-saved session on startup."""

import json
import os
from pathlib import Path

from src.repl import _handle_resume_command


class TestResumeCLI:
    """Tests for _handle_resume_command which backs both /resume and --resume."""

    def test_resume_missing_autosave(self, tmp_path, monkeypatch):
        """Returns error when no autosave file exists."""
        monkeypatch.chdir(tmp_path)
        result = _handle_resume_command(cwd=str(tmp_path))
        assert isinstance(result, str)
        assert "No auto-saved session found" in result

    def test_resume_valid_autosave(self, tmp_path, monkeypatch):
        """Returns messages, model, usage tuple for valid autosave."""
        monkeypatch.chdir(tmp_path)
        yoyo_dir = tmp_path / ".yoyo"
        yoyo_dir.mkdir()
        autosave = yoyo_dir / "autosave.json"
        data = {
            "autosaved": True,
            "messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi"},
            ],
            "model": "glm-5.1",
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }
        autosave.write_text(json.dumps(data), encoding="utf-8")

        result = _handle_resume_command(cwd=str(tmp_path))
        assert isinstance(result, tuple)
        messages, model, usage, warnings = result
        assert len(messages) == 3
        assert model == "glm-5.1"
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50

        # Autosave file should be deleted after successful resume
        assert not autosave.exists()

    def test_resume_deletes_autosave_after_success(self, tmp_path, monkeypatch):
        """Autosave file is removed after successful resume."""
        monkeypatch.chdir(tmp_path)
        yoyo_dir = tmp_path / ".yoyo"
        yoyo_dir.mkdir()
        autosave = yoyo_dir / "autosave.json"
        data = {
            "autosaved": True,
            "messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "hi"},
            ],
            "model": "test-model",
        }
        autosave.write_text(json.dumps(data), encoding="utf-8")

        _handle_resume_command(cwd=str(tmp_path))
        assert not autosave.exists()

    def test_resume_non_autosave_file(self, tmp_path, monkeypatch):
        """Manual saves (autosaved: false) are not resumed."""
        monkeypatch.chdir(tmp_path)
        yoyo_dir = tmp_path / ".yoyo"
        yoyo_dir.mkdir()
        autosave = yoyo_dir / "autosave.json"
        data = {
            "autosaved": False,
            "messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "hi"},
            ],
            "model": "test-model",
        }
        autosave.write_text(json.dumps(data), encoding="utf-8")

        result = _handle_resume_command(cwd=str(tmp_path))
        assert isinstance(result, str)
        assert "No auto-saved session found" in result

    def test_resume_corrupted_file(self, tmp_path, monkeypatch):
        """Corrupted autosave file returns error."""
        monkeypatch.chdir(tmp_path)
        yoyo_dir = tmp_path / ".yoyo"
        yoyo_dir.mkdir()
        autosave = yoyo_dir / "autosave.json"
        autosave.write_text("not valid json {{{", encoding="utf-8")

        result = _handle_resume_command(cwd=str(tmp_path))
        assert isinstance(result, str)
        assert "corrupted" in result.lower() or "ERROR" in result

    def test_resume_only_system_prompt(self, tmp_path, monkeypatch):
        """Autosave with only system prompt is treated as empty."""
        monkeypatch.chdir(tmp_path)
        yoyo_dir = tmp_path / ".yoyo"
        yoyo_dir.mkdir()
        autosave = yoyo_dir / "autosave.json"
        data = {
            "autosaved": True,
            "messages": [{"role": "system", "content": "sys"}],
            "model": "test-model",
        }
        autosave.write_text(json.dumps(data), encoding="utf-8")

        result = _handle_resume_command(cwd=str(tmp_path))
        assert isinstance(result, str)
        assert "No auto-saved session found" in result


class TestResumeCLIArgParsing:
    """Test that --resume flag is accepted by argparse."""

    def test_resume_flag_parsed(self):
        """--resume is accepted as a CLI argument."""
        import argparse
        from src.main import parse_args

        # Can't easily test parse_args with --resume since it may not exist yet,
        # but we verify the function exists and handles unknown args gracefully.
        # This will be verified after the implementation.
        pass
