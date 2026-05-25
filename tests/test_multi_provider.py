"""Tests for multi-provider support."""

import os
from unittest.mock import patch

from src.provider import PROVIDER_PRESETS, resolve_provider_config, GLMProvider


class TestProviderPresets:
    """Test provider preset definitions."""

    def test_glm_preset_exists(self):
        assert "glm" in PROVIDER_PRESETS

    def test_openai_preset_exists(self):
        assert "openai" in PROVIDER_PRESETS

    def test_deepseek_preset_exists(self):
        assert "deepseek" in PROVIDER_PRESETS

    def test_all_presets_have_required_fields(self):
        for name, preset in PROVIDER_PRESETS.items():
            assert "base_url" in preset, f"Provider {name} missing base_url"
            assert "env_key" in preset, f"Provider {name} missing env_key"
            assert "default_model" in preset, f"Provider {name} missing default_model"

    def test_preset_base_urls_are_valid(self):
        for name, preset in PROVIDER_PRESETS.items():
            url = preset["base_url"]
            assert url.startswith("https://"), f"Provider {name} base_url should be https"


class TestResolveProviderConfig:
    """Test resolving provider configuration from preset name."""

    def test_resolve_glm(self):
        config = resolve_provider_config("glm")
        assert config["base_url"] == "https://open.bigmodel.cn/api/paas/v4"
        assert config["env_key"] == "GLM_API_KEY"
        assert config["default_model"] == "glm-5.1"

    def test_resolve_openai(self):
        config = resolve_provider_config("openai")
        assert config["base_url"] == "https://api.openai.com/v1"
        assert config["env_key"] == "OPENAI_API_KEY"
        assert config["default_model"] == "gpt-4o"

    def test_resolve_deepseek(self):
        config = resolve_provider_config("deepseek")
        assert "deepseek" in config["base_url"]
        assert config["env_key"] == "DEEPSEEK_API_KEY"

    def test_resolve_unknown_provider(self):
        """Unknown provider name should raise ValueError."""
        try:
            resolve_provider_config("nonexistent_provider")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "nonexistent_provider" in str(e)

    def test_resolve_case_insensitive(self):
        """Provider name resolution should be case-insensitive."""
        config1 = resolve_provider_config("OpenAI")
        config2 = resolve_provider_config("openai")
        assert config1["base_url"] == config2["base_url"]


class TestGLMProviderWithPreset:
    """Test that GLMProvider works with different provider configs."""

    @patch.dict(os.environ, {"GLM_API_KEY": "test-key"})
    def test_default_provider_still_works(self):
        """Existing GLM provider creation should still work."""
        provider = GLMProvider()
        assert provider.model == "glm-5.1"
        assert provider.base_url == "https://open.bigmodel.cn/api/paas/v4"

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-key"})
    def test_openai_provider_via_explicit_config(self):
        """Create provider with OpenAI config by passing api_key and base_url."""
        config = resolve_provider_config("openai")
        provider = GLMProvider(
            api_key=os.environ.get("OPENAI_API_KEY"),
            base_url=config["base_url"],
            model=config["default_model"],
        )
        assert provider.model == "gpt-4o"
        assert provider.base_url == "https://api.openai.com/v1"
        assert provider.api_key == "sk-test-key"

    @patch.dict(os.environ, {"DEEPSEEK_API_KEY": "ds-test-key"})
    def test_deepseek_provider_via_explicit_config(self):
        """Create provider with DeepSeek config."""
        config = resolve_provider_config("deepseek")
        provider = GLMProvider(
            api_key=os.environ.get("DEEPSEEK_API_KEY"),
            base_url=config["base_url"],
            model=config["default_model"],
        )
        assert "deepseek" in provider.base_url
        assert provider.api_key == "ds-test-key"
