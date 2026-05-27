"""Test that provider preset name is stored and accessible."""

import os
import pytest
from unittest.mock import patch

from src.provider import GLMProvider


class TestProviderName:
    """Verify _provider_name is stored on GLMProvider."""

    def test_glm_provider_stores_name(self):
        """GLMProvider with provider='glm' stores _provider_name='glm'."""
        with patch.dict(os.environ, {"GLM_API_KEY": "test-key-12345678"}):
            p = GLMProvider(provider="glm")
            assert p._provider_name == "glm"

    def test_openai_provider_stores_name(self):
        """GLMProvider with provider='openai' stores _provider_name='openai'."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key-12345678"}):
            p = GLMProvider(provider="openai")
            assert p._provider_name == "openai"

    def test_deepseek_provider_stores_name(self):
        """GLMProvider with provider='deepseek' stores _provider_name='deepseek'."""
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key-12345678"}):
            p = GLMProvider(provider="deepseek")
            assert p._provider_name == "deepseek"

    def test_no_provider_stores_none(self):
        """GLMProvider without provider arg stores _provider_name=None."""
        with patch.dict(os.environ, {"GLM_API_KEY": "test-key-12345678"}):
            p = GLMProvider()
            assert p._provider_name is None

    def test_env_command_shows_provider_name(self):
        """_show_env_info shows the actual provider name, not 'custom'."""
        from src.repl import _show_env_info

        output = _show_env_info(
            model="glm-5.1",
            base_url="https://open.bigmodel.cn/api/paas/v4",
            provider="glm",
            api_key="test-key-12345678",
        )
        assert "glm" in output
        assert "Provider: glm" in output

    def test_env_command_shows_custom_when_no_provider(self):
        """_show_env_info shows 'custom' when provider is None."""
        from src.repl import _show_env_info

        output = _show_env_info(
            model="my-model",
            base_url="https://custom.api.com/v1",
            provider=None,
            api_key="test-key-12345678",
        )
        assert "Provider: custom" in output
