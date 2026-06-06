"""Tests for persistent config settings across sessions.

Settings like temperature, max_tokens, and top_p should persist
between sessions via .yoyo/config.json.
"""

import json
import os
import tempfile
import pytest

from src.repl import _load_persistent_config, _save_persistent_config


class TestPersistentConfig:
    """Config persistence via .yoyo/config.json."""

    def test_save_and_load_round_trip(self, tmp_path):
        """Saving config and loading it back should preserve values."""
        config_dir = tmp_path / ".yoyo"
        config_dir.mkdir()
        config_file = config_dir / "config.json"

        settings = {"temperature": 0.7, "max_tokens": 4096, "top_p": 0.95}
        _save_persistent_config(settings, config_path=str(config_file))

        loaded = _load_persistent_config(config_path=str(config_file))
        assert loaded["temperature"] == 0.7
        assert loaded["max_tokens"] == 4096
        assert loaded["top_p"] == 0.95

    def test_load_missing_file_returns_empty(self, tmp_path):
        """Loading from a nonexistent file should return empty dict."""
        config_file = tmp_path / ".yoyo" / "config.json"
        loaded = _load_persistent_config(config_path=str(config_file))
        assert loaded == {}

    def test_load_corrupt_json_returns_empty(self, tmp_path):
        """Loading corrupt JSON should return empty dict, not crash."""
        config_dir = tmp_path / ".yoyo"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        config_file.write_text("{bad json")
        loaded = _load_persistent_config(config_path=str(config_file))
        assert loaded == {}

    def test_save_creates_directory(self, tmp_path):
        """Saving should create .yoyo/ directory if it doesn't exist."""
        config_file = tmp_path / ".yoyo" / "config.json"
        _save_persistent_config(
            {"temperature": 0.5},
            config_path=str(config_file),
        )
        assert config_file.exists()
        data = json.loads(config_file.read_text())
        assert data["temperature"] == 0.5

    def test_save_partial_update(self, tmp_path):
        """Saving with new values should merge with existing config."""
        config_dir = tmp_path / ".yoyo"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({"temperature": 0.7, "max_tokens": 4096}))

        _save_persistent_config(
            {"temperature": 0.9},
            config_path=str(config_file),
        )
        data = json.loads(config_file.read_text())
        assert data["temperature"] == 0.9
        assert data["max_tokens"] == 4096  # Preserved

    def test_load_ignores_invalid_keys(self, tmp_path):
        """Loading should ignore keys that aren't valid config settings."""
        config_dir = tmp_path / ".yoyo"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({
            "temperature": 0.7,
            "invalid_key": "should be ignored",
            "max_tokens": 2048,
        }))

        loaded = _load_persistent_config(config_path=str(config_file))
        assert "temperature" in loaded
        assert "max_tokens" in loaded
        assert "invalid_key" not in loaded

    def test_save_validates_temperature_range(self, tmp_path):
        """Temperature outside 0.0-2.0 should be clamped."""
        config_dir = tmp_path / ".yoyo"
        config_dir.mkdir()
        config_file = config_dir / "config.json"

        _save_persistent_config(
            {"temperature": 5.0},
            config_path=str(config_file),
        )
        data = json.loads(config_file.read_text())
        assert data["temperature"] == 2.0

    def test_save_validates_top_p_range(self, tmp_path):
        """top_p outside 0.0-1.0 should be clamped."""
        config_dir = tmp_path / ".yoyo"
        config_dir.mkdir()
        config_file = config_dir / "config.json"

        _save_persistent_config(
            {"top_p": -0.5},
            config_path=str(config_file),
        )
        data = json.loads(config_file.read_text())
        assert data["top_p"] == 0.0

    def test_save_validates_max_tokens_positive(self, tmp_path):
        """max_tokens must be positive."""
        config_dir = tmp_path / ".yoyo"
        config_dir.mkdir()
        config_file = config_dir / "config.json"

        _save_persistent_config(
            {"max_tokens": -100},
            config_path=str(config_file),
        )
        data = json.loads(config_file.read_text())
        # Should not save invalid value — either skip or clamp
        assert data.get("max_tokens") is None or data["max_tokens"] > 0
