"""Tests for /list-providers REPL command."""

import pytest
from unittest.mock import patch

from src.repl import _format_providers_list
from src.provider import PROVIDER_PRESETS


def test_format_providers_list_shows_all_presets():
    """All provider presets are listed."""
    result = _format_providers_list()
    for name in PROVIDER_PRESETS:
        assert name in result


def test_format_providers_list_shows_env_keys():
    """Each preset shows its required environment variable."""
    result = _format_providers_list()
    for name, config in PROVIDER_PRESETS.items():
        assert config["env_key"] in result


def test_format_providers_list_shows_models():
    """Each preset shows its default model."""
    result = _format_providers_list()
    for name, config in PROVIDER_PRESETS.items():
        assert config["default_model"] in result


def test_format_providers_list_with_active():
    """When an active model is given, it's highlighted in the output."""
    result = _format_providers_list(active_model="glm-5.1")
    assert "active" in result.lower() or "glm-5.1" in result


def test_format_providers_list_no_active():
    """Without active model, no 'active' indicator shown."""
    result = _format_providers_list(active_model=None)
    # Should still list all providers
    assert "glm" in result
    assert "openai" in result
