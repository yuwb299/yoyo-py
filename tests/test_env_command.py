"""Tests for /env command — show provider configuration."""

import os
import pytest
from unittest.mock import patch

from src.repl import _show_env_info


class TestShowEnvInfo:
    """Test the /env command output."""

    def test_shows_model(self):
        output = _show_env_info(
            model="glm-5.1",
            base_url="https://open.bigmodel.cn/api/paas/v4",
            provider="glm",
        )
        assert "glm-5.1" in output
        assert "Model" in output

    def test_shows_base_url(self):
        output = _show_env_info(
            model="gpt-4o",
            base_url="https://api.openai.com/v1",
            provider="openai",
        )
        assert "api.openai.com" in output
        assert "Base URL" in output

    def test_shows_provider(self):
        output = _show_env_info(
            model="deepseek-chat",
            base_url="https://api.deepseek.com/v1",
            provider="deepseek",
        )
        assert "deepseek" in output

    def test_masks_api_key_full(self):
        """Full API key should never appear in output."""
        output = _show_env_info(
            model="glm-5.1",
            base_url="https://open.bigmodel.cn/api/paas/v4",
            provider="glm",
            api_key="sk-supersecret123456789",
        )
        assert "supersecret" not in output

    def test_shows_api_key_prefix(self):
        """Should show first few chars of API key for verification."""
        output = _show_env_info(
            model="glm-5.1",
            base_url="https://open.bigmodel.cn/api/paas/v4",
            provider="glm",
            api_key="sk-abcdef1234567890",
        )
        assert "sk-a" in output  # First 4 chars shown
        assert "1234567890" not in output

    def test_handles_empty_api_key(self):
        output = _show_env_info(
            model="glm-5.1",
            base_url="https://open.bigmodel.cn/api/paas/v4",
            provider="glm",
            api_key="",
        )
        assert "not set" in output or "empty" in output or "***" in output

    def test_short_api_key_shows_asterisks(self):
        """Very short keys should still be masked safely."""
        output = _show_env_info(
            model="glm-5.1",
            base_url="https://open.bigmodel.cn/api/paas/v4",
            provider="glm",
            api_key="ab",
        )
        assert "ab" not in output or "***" in output

    def test_no_provider_shows_custom(self):
        output = _show_env_info(
            model="my-model",
            base_url="https://custom.api.com/v1",
            provider=None,
        )
        assert "custom" in output.lower() or "Custom" in output
