"""Tests for provider failover."""

import os
from unittest.mock import patch, MagicMock

from openai import RateLimitError, APIConnectionError

from src.provider import GLMProvider, APIError, PROVIDER_PRESETS


class TestProviderFailover:
    """Test that provider failover works when primary API fails."""

    @patch("time.sleep")  # Mock sleep to avoid real delays in retry loop
    @patch.dict(os.environ, {"GLM_API_KEY": "test-glm-key", "OPENAI_API_KEY": "test-openai-key"})
    def test_failover_to_secondary_on_rate_limit(self, mock_sleep):
        """When primary hits rate limit after retries, fall back to secondary."""
        primary = GLMProvider(provider="glm")
        secondary = GLMProvider(provider="openai")

        from src.provider import FailoverProvider
        fp = FailoverProvider([primary, secondary])

        mock_stream = iter([])
        primary.client = MagicMock()
        primary.client.chat.completions.create.side_effect = RateLimitError(
            message="rate limited", response=MagicMock(status_code=429), body=None
        )
        secondary.client = MagicMock()
        secondary.client.chat.completions.create.return_value = mock_stream

        result = fp.chat(messages=[{"role": "user", "content": "test"}])
        # Should have called secondary after primary failed
        assert secondary.client.chat.completions.create.called

    @patch.dict(os.environ, {"GLM_API_KEY": "test-glm-key"})
    def test_failover_single_provider_no_crash(self):
        """FailoverProvider with a single provider still works (no failover, just normal)."""
        primary = GLMProvider(provider="glm")
        from src.provider import FailoverProvider
        fp = FailoverProvider([primary])
        assert len(fp.providers) == 1

    @patch("time.sleep")
    @patch.dict(os.environ, {"GLM_API_KEY": "test-key", "OPENAI_API_KEY": "sk-test"})
    def test_failover_all_providers_fail(self, mock_sleep):
        """When all providers fail, raise the last error."""
        primary = GLMProvider(provider="glm")
        secondary = GLMProvider(provider="openai")
        from src.provider import FailoverProvider
        fp = FailoverProvider([primary, secondary])

        primary.client = MagicMock()
        primary.client.chat.completions.create.side_effect = RateLimitError(
            message="rate limited", response=MagicMock(status_code=429), body=None
        )
        secondary.client = MagicMock()
        secondary.client.chat.completions.create.side_effect = RateLimitError(
            message="also rate limited", response=MagicMock(status_code=429), body=None
        )

        try:
            fp.chat(messages=[{"role": "user", "content": "test"}])
            assert False, "Should have raised APIError"
        except APIError as e:
            assert "rate_limit" in str(e) or "all providers" in str(e).lower()

    @patch("time.sleep")
    @patch.dict(os.environ, {"GLM_API_KEY": "test-key", "OPENAI_API_KEY": "sk-test"})
    def test_failover_non_retryable_error_no_fallback(self, mock_sleep):
        """Non-retryable errors (auth) should NOT trigger failover."""
        primary = GLMProvider(provider="glm")
        secondary = GLMProvider(provider="openai")
        from src.provider import FailoverProvider
        fp = FailoverProvider([primary, secondary])

        from openai import AuthenticationError
        primary.client = MagicMock()
        primary.client.chat.completions.create.side_effect = AuthenticationError(
            message="bad key", response=MagicMock(status_code=401), body=None
        )
        secondary.client = MagicMock()

        try:
            fp.chat(messages=[{"role": "user", "content": "test"}])
            assert False, "Should have raised APIError"
        except APIError as e:
            assert e.category == "auth"
            # Secondary should NOT have been called
            assert not secondary.client.chat.completions.create.called

    @patch.dict(os.environ, {"GLM_API_KEY": "test-key", "OPENAI_API_KEY": "sk-test"})
    def test_failover_primary_succeeds(self):
        """When primary succeeds, don't call secondary."""
        primary = GLMProvider(provider="glm")
        secondary = GLMProvider(provider="openai")
        from src.provider import FailoverProvider
        fp = FailoverProvider([primary, secondary])

        mock_stream = iter([])
        primary.client = MagicMock()
        primary.client.chat.completions.create.return_value = mock_stream
        secondary.client = MagicMock()

        result = fp.chat(messages=[{"role": "user", "content": "test"}])
        assert primary.client.chat.completions.create.called
        assert not secondary.client.chat.completions.create.called
