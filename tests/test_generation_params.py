"""Tests for generation parameters (temperature, max_tokens) in provider."""

import os
from unittest.mock import patch, MagicMock

from src.provider import GLMProvider


class TestGenerationParams:
    """Test that generation parameters are passed through correctly."""

    @patch.dict(os.environ, {"GLM_API_KEY": "test-key"}, clear=True)
    def test_default_params_no_extras(self):
        """Without any generation params, kwargs should not include them."""
        provider = GLMProvider()
        provider.client = MagicMock()
        mock_stream = MagicMock()
        provider.client.chat.completions.create.return_value = mock_stream

        provider.chat([{"role": "user", "content": "hi"}])

        call_kwargs = provider.client.chat.completions.create.call_args[1]
        assert "temperature" not in call_kwargs
        assert "max_tokens" not in call_kwargs
        assert "top_p" not in call_kwargs

    @patch.dict(os.environ, {"GLM_API_KEY": "test-key"}, clear=True)
    def test_max_tokens_passed_through(self):
        """max_tokens should be forwarded to the API when set."""
        provider = GLMProvider(max_tokens=4096)
        provider.client = MagicMock()
        provider.client.chat.completions.create.return_value = MagicMock()

        provider.chat([{"role": "user", "content": "hi"}])

        call_kwargs = provider.client.chat.completions.create.call_args[1]
        assert call_kwargs["max_tokens"] == 4096

    @patch.dict(os.environ, {"GLM_API_KEY": "test-key"}, clear=True)
    def test_temperature_passed_through(self):
        """temperature should be forwarded to the API when set."""
        provider = GLMProvider(temperature=0.0)
        provider.client = MagicMock()
        provider.client.chat.completions.create.return_value = MagicMock()

        provider.chat([{"role": "user", "content": "hi"}])

        call_kwargs = provider.client.chat.completions.create.call_args[1]
        assert call_kwargs["temperature"] == 0.0

    @patch.dict(os.environ, {"GLM_API_KEY": "test-key"}, clear=True)
    def test_top_p_passed_through(self):
        """top_p should be forwarded to the API when set."""
        provider = GLMProvider(top_p=0.9)
        provider.client = MagicMock()
        provider.client.chat.completions.create.return_value = MagicMock()

        provider.chat([{"role": "user", "content": "hi"}])

        call_kwargs = provider.client.chat.completions.create.call_args[1]
        assert call_kwargs["top_p"] == 0.9

    @patch.dict(os.environ, {"GLM_API_KEY": "test-key"}, clear=True)
    def test_all_params_together(self):
        """All generation params should work together."""
        provider = GLMProvider(max_tokens=8192, temperature=0.7, top_p=0.95)
        provider.client = MagicMock()
        provider.client.chat.completions.create.return_value = MagicMock()

        provider.chat([{"role": "user", "content": "hi"}])

        call_kwargs = provider.client.chat.completions.create.call_args[1]
        assert call_kwargs["max_tokens"] == 8192
        assert call_kwargs["temperature"] == 0.7
        assert call_kwargs["top_p"] == 0.95

    @patch.dict(os.environ, {"GLM_API_KEY": "test-key"}, clear=True)
    def test_max_tokens_none_not_passed(self):
        """max_tokens=None should not be included in kwargs."""
        provider = GLMProvider(max_tokens=None)
        provider.client = MagicMock()
        provider.client.chat.completions.create.return_value = MagicMock()

        provider.chat([{"role": "user", "content": "hi"}])

        call_kwargs = provider.client.chat.completions.create.call_args[1]
        assert "max_tokens" not in call_kwargs

    @patch.dict(os.environ, {"GLM_API_KEY": "test-key"}, clear=True)
    def test_params_persist_across_calls(self):
        """Generation params should persist across multiple chat calls."""
        provider = GLMProvider(temperature=0.0, max_tokens=2048)
        provider.client = MagicMock()
        provider.client.chat.completions.create.return_value = MagicMock()

        provider.chat([{"role": "user", "content": "hi"}])
        provider.chat([{"role": "user", "content": "hello"}])

        assert provider.client.chat.completions.create.call_count == 2
        for call in provider.client.chat.completions.create.call_args_list:
            kwargs = call[1]
            assert kwargs["temperature"] == 0.0
            assert kwargs["max_tokens"] == 2048

    @patch.dict(os.environ, {"GLM_API_KEY": "test-key"}, clear=True)
    def test_temperature_env_override(self):
        """GLM_TEMPERATURE env var should set default temperature."""
        with patch.dict(os.environ, {"GLM_TEMPERATURE": "0.5"}):
            provider = GLMProvider()
            assert provider.temperature == 0.5

    @patch.dict(os.environ, {"GLM_API_KEY": "test-key"}, clear=True)
    def test_max_tokens_env_override(self):
        """GLM_MAX_TOKENS env var should set default max_tokens."""
        with patch.dict(os.environ, {"GLM_MAX_TOKENS": "4096"}):
            provider = GLMProvider()
            assert provider.max_tokens == 4096

    @patch.dict(os.environ, {"GLM_API_KEY": "test-key"}, clear=True)
    def test_explicit_params_override_env(self):
        """Explicit constructor args should override env vars."""
        with patch.dict(os.environ, {"GLM_TEMPERATURE": "0.5", "GLM_MAX_TOKENS": "4096"}):
            provider = GLMProvider(temperature=0.0, max_tokens=8192)
            assert provider.temperature == 0.0
            assert provider.max_tokens == 8192
