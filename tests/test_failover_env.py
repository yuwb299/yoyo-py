"""Test that /env command doesn't crash with FailoverProvider."""

import os
import pytest
from unittest.mock import patch, MagicMock

from src.provider import GLMProvider, FailoverProvider
from src.repl import _show_env_info


class TestEnvWithFailoverProvider:
    """Verify /env works with FailoverProvider (doesn't crash)."""

    def _make_failover_provider(self):
        """Create a FailoverProvider with mock providers for testing."""
        with patch.dict(os.environ, {
            "GLM_API_KEY": "test-key-12345678",
            "DEEPSEEK_API_KEY": "test-key-87654321",
        }):
            p1 = GLMProvider(provider="glm")
            p2 = GLMProvider(provider="deepseek")
            return FailoverProvider([p1, p2])

    def test_failover_provider_env_no_crash(self):
        """_show_env_info should not crash when called with FailoverProvider attrs."""
        fp = self._make_failover_provider()
        # This simulates what /env does — get attrs from provider
        # Should not raise AttributeError
        output = _show_env_info(
            model=fp.model,
            base_url=getattr(fp, 'base_url', '(multiple)'),
            provider=getattr(fp, '_provider_name', None),
            api_key=getattr(fp, 'api_key', '(multiple)'),
            max_tokens=getattr(fp, 'max_tokens', None),
            temperature=getattr(fp, 'temperature', None),
            top_p=getattr(fp, 'top_p', None),
        )
        assert "failover" in output.lower() or "multiple" in output.lower() or "glm" in output.lower()

    def test_failover_provider_has_provider_names(self):
        """FailoverProvider should expose _provider_names for /env display."""
        fp = self._make_failover_provider()
        # Check that we can get provider names
        names = [p._provider_name for p in fp.providers if p._provider_name]
        assert "glm" in names
        assert "deepseek" in names
