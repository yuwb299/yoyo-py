"""Tests for the GLMProvider — error classification, retry logic, and usage parsing."""

import pytest
from unittest.mock import MagicMock, patch

from src.provider import APIError, Usage, _classify_api_error, GLMProvider


class TestAPIError:
    def test_str_includes_category(self):
        err = APIError("something broke", category="rate_limit", retryable=True)
        assert "[rate_limit]" in str(err)
        assert "something broke" in str(err)

    def test_retryable_flag(self):
        err = APIError("x", category="test", retryable=True)
        assert err.retryable is True

    def test_not_retryable_by_default(self):
        err = APIError("x", category="test")
        assert err.retryable is False


class TestClassifyAPIError:
    def test_rate_limit_error(self):
        from openai import RateLimitError
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        err = RateLimitError(response=mock_resp, message="slow down", body=None)
        result = _classify_api_error(err)
        assert result.category == "rate_limit"
        assert result.retryable is True

    def test_authentication_error(self):
        from openai import AuthenticationError
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        err = AuthenticationError(response=mock_resp, message="bad key", body=None)
        result = _classify_api_error(err)
        assert result.category == "auth"
        assert result.retryable is False

    def test_connection_error(self):
        from openai import APIConnectionError
        err = APIConnectionError(request=MagicMock())
        result = _classify_api_error(err)
        assert result.category == "connection"
        assert result.retryable is True

    def test_timeout_error(self):
        from openai import APITimeoutError
        err = APITimeoutError(request=MagicMock())
        result = _classify_api_error(err)
        assert result.category == "timeout"
        assert result.retryable is True

    def test_bad_request_error(self):
        from openai import BadRequestError
        mock_resp = MagicMock()
        err = BadRequestError(response=mock_resp, message="bad", body=None)
        result = _classify_api_error(err)
        assert result.category == "bad_request"
        assert result.retryable is False

    def test_internal_server_error(self):
        from openai import InternalServerError
        mock_resp = MagicMock()
        err = InternalServerError(response=mock_resp, message="oops", body=None)
        result = _classify_api_error(err)
        assert result.category == "server_error"
        assert result.retryable is True

    def test_unknown_error(self):
        err = RuntimeError("something unexpected")
        result = _classify_api_error(err)
        assert result.category == "unknown"
        assert result.retryable is False


class TestUsage:
    def test_add_accumulates(self):
        u1 = Usage(input_tokens=10, output_tokens=20)
        u2 = Usage(input_tokens=5, output_tokens=15)
        u1.add(u2)
        assert u1.input_tokens == 15
        assert u1.output_tokens == 35

    def test_str_format(self):
        u = Usage(input_tokens=100, output_tokens=200)
        assert str(u) == "100 in / 200 out"

    def test_default_zero(self):
        u = Usage()
        assert u.input_tokens == 0
        assert u.output_tokens == 0


class TestGLMProviderParseUsage:
    def test_parse_usage_with_data(self):
        mock_resp = MagicMock()
        mock_resp.usage.prompt_tokens = 50
        mock_resp.usage.completion_tokens = 25
        result = GLMProvider.parse_usage(mock_resp)
        assert result.input_tokens == 50
        assert result.output_tokens == 25

    def test_parse_usage_none(self):
        mock_resp = MagicMock()
        mock_resp.usage = None
        result = GLMProvider.parse_usage(mock_resp)
        assert result.input_tokens == 0
        assert result.output_tokens == 0

    def test_parse_usage_missing_attr(self):
        mock_resp = MagicMock(spec=[])  # No attributes
        result = GLMProvider.parse_usage(mock_resp)
        assert result.input_tokens == 0

    def test_parse_usage_zero_values(self):
        mock_resp = MagicMock()
        mock_resp.usage.prompt_tokens = 0
        mock_resp.usage.completion_tokens = 0
        result = GLMProvider.parse_usage(mock_resp)
        assert result.input_tokens == 0
        assert result.output_tokens == 0


class TestGLMProviderInit:
    def test_missing_api_key_raises(self):
        """Provider should raise ValueError if no API key is configured."""
        with patch.dict("os.environ", {}, clear=True):
            # Remove GLM_API_KEY from env
            import os
            os.environ.pop("GLM_API_KEY", None)
            with pytest.raises(ValueError, match="GLM_API_KEY"):
                GLMProvider(api_key="")

    def test_custom_model(self):
        """Provider should accept custom model name."""
        provider = GLMProvider(api_key="test-key", model="custom-model")
        assert provider.model == "custom-model"

    def test_custom_base_url(self):
        """Provider should accept custom base URL."""
        provider = GLMProvider(api_key="test-key", base_url="https://custom.api.com/v1")
        assert provider.base_url == "https://custom.api.com/v1"
