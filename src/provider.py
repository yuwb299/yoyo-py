"""API provider — OpenAI-compatible interface supporting multiple LLM providers.

Supports GLM 5, OpenAI, DeepSeek, and any OpenAI-compatible API.
Provider presets simplify configuration: just set the right API key env var
and pass --provider <name> to select the backend.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI


# ── Provider presets ────────────────────────────────────────────────────
# Each preset defines: base_url, env_key (for API key), default_model
# Any OpenAI-compatible API can be used by setting --base-url and the
# appropriate API key environment variable directly.

PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "glm": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "env_key": "GLM_API_KEY",
        "default_model": "glm-5.1",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "env_key": "OPENAI_API_KEY",
        "default_model": "gpt-4o",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "env_key": "DEEPSEEK_API_KEY",
        "default_model": "deepseek-chat",
    },
    "moonshot": {
        "base_url": "https://api.moonshot.cn/v1",
        "env_key": "MOONSHOT_API_KEY",
        "default_model": "moonshot-v1-8k",
    },
    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "env_key": "GLM_API_KEY",
        "default_model": "glm-4-plus",
    },
}


def _env_int(name: str) -> int | None:
    """Read an integer from an environment variable, or None if unset/invalid."""
    val = os.getenv(name)
    if val is not None:
        try:
            return int(val)
        except ValueError:
            pass
    return None


def _env_float(name: str) -> float | None:
    """Read a float from an environment variable, or None if unset/invalid."""
    val = os.getenv(name)
    if val is not None:
        try:
            return float(val)
        except ValueError:
            pass
    return None


def resolve_provider_config(provider_name: str) -> dict[str, str]:
    """Resolve a provider preset name to its configuration.

    Args:
        provider_name: Provider name (case-insensitive). E.g. "glm", "openai", "deepseek".

    Returns:
        Dict with base_url, env_key, default_model.

    Raises:
        ValueError: If provider_name is not a known preset.
    """
    key = provider_name.lower()
    if key not in PROVIDER_PRESETS:
        available = ", ".join(sorted(PROVIDER_PRESETS.keys()))
        raise ValueError(
            f"Unknown provider '{provider_name}'. Available providers: {available}"
        )
    return PROVIDER_PRESETS[key]


@dataclass
class Usage:
    """Token usage tracking."""
    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, other: Usage) -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens

    def __str__(self) -> str:
        return f"{self.input_tokens} in / {self.output_tokens} out"


class APIError(Exception):
    """Structured API error with category and retry hint."""

    def __init__(self, message: str, category: str = "unknown", retryable: bool = False):
        super().__init__(message)
        self.category = category
        self.retryable = retryable

    def __str__(self) -> str:
        return f"[{self.category}] {super().__str__()}"


def _classify_api_error(error: Exception) -> APIError:
    """Classify an API error into a structured APIError."""
    from openai import (
        AuthenticationError,
        RateLimitError,
        APIConnectionError,
        APITimeoutError,
        BadRequestError,
        InternalServerError,
    )

    if isinstance(error, RateLimitError):
        return APIError(
            f"Rate limited: {error}",
            category="rate_limit",
            retryable=True,
        )
    elif isinstance(error, AuthenticationError):
        return APIError(
            f"Authentication failed: {error}",
            category="auth",
            retryable=False,
        )
    elif isinstance(error, APITimeoutError):
        # Must check before APIConnectionError since APITimeoutError inherits from it
        return APIError(
            f"Request timed out: {error}",
            category="timeout",
            retryable=True,
        )
    elif isinstance(error, APIConnectionError):
        return APIError(
            f"Connection error: {error}",
            category="connection",
            retryable=True,
        )
    elif isinstance(error, BadRequestError):
        return APIError(
            f"Bad request: {error}",
            category="bad_request",
            retryable=False,
        )
    elif isinstance(error, InternalServerError):
        return APIError(
            f"Server error: {error}",
            category="server_error",
            retryable=True,
        )
    else:
        return APIError(
            f"Unexpected error: {error}",
            category="unknown",
            retryable=False,
        )


class GLMProvider:
    """GLM 5 provider via OpenAI-compatible API."""

    # Retry configuration
    MAX_RETRIES = 3
    RETRY_DELAYS = [1, 3, 6]  # Exponential backoff in seconds

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
    ):
        # Store provider preset name so /env can show which preset is active
        self._provider_name = provider if provider else None

        # Resolve provider preset if given
        if provider:
            preset = resolve_provider_config(provider)
            self.base_url = base_url or os.getenv("GLM_BASE_URL", preset["base_url"])
            self.model = model or os.getenv("GLM_MODEL", preset["default_model"])
            self.api_key = api_key or os.getenv(preset["env_key"], "")
        else:
            self.api_key = api_key or os.getenv("GLM_API_KEY", "")
            self.base_url = base_url or os.getenv(
                "GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"
            )
            self.model = model or os.getenv("GLM_MODEL", "glm-5.1")

        if not self.api_key:
            env_var = preset["env_key"] if provider else "GLM_API_KEY"
            raise ValueError(
                f"{env_var} is required. Set it in .env or pass to constructor."
            )

        # Generation parameters: explicit args override env vars
        self.max_tokens = max_tokens if max_tokens is not None else _env_int("GLM_MAX_TOKENS")
        self.temperature = temperature if temperature is not None else _env_float("GLM_TEMPERATURE")
        self.top_p = top_p if top_p is not None else _env_float("GLM_TOP_P")

        # Reasoning effort: controls extended thinking depth for models that support it
        # Valid values: None (use API default), "low", "medium", "high"
        self.reasoning_effort: str | None = None

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        stream: bool = True,
    ) -> Any:
        """Send a chat completion request with automatic retry for transient errors.

        Returns a stream if stream=True, else a completion object.
        Raises APIError for non-retryable errors or after exhausting retries.
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        # Only include generation params when explicitly set — APIs may reject
        # unknown or None-valued params differently
        if self.max_tokens is not None:
            kwargs["max_tokens"] = self.max_tokens
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        if self.top_p is not None:
            kwargs["top_p"] = self.top_p
        if self.reasoning_effort is not None:
            kwargs["reasoning_effort"] = self.reasoning_effort

        last_error: APIError | None = None
        for attempt in range(self.MAX_RETRIES):
            try:
                return self.client.chat.completions.create(**kwargs)
            except Exception as e:
                api_error = _classify_api_error(e)
                last_error = api_error

                if not api_error.retryable:
                    raise api_error

                if attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_DELAYS[attempt]
                    time.sleep(delay)

        # All retries exhausted
        raise last_error or APIError("All retries exhausted", category="retry_exhausted", retryable=False)

    @staticmethod
    def parse_usage(response: Any) -> Usage:
        """Extract token usage from a response chunk or final response."""
        if hasattr(response, "usage") and response.usage:
            return Usage(
                input_tokens=getattr(response.usage, "prompt_tokens", 0) or 0,
                output_tokens=getattr(response.usage, "completion_tokens", 0) or 0,
            )
        return Usage()


class FailoverProvider:
    """Provider that tries multiple API backends in order, falling back on failure.

    When the primary provider fails with a retryable error (rate limit, timeout,
    connection error), the next provider in the list is tried. Non-retryable
    errors (auth, bad request) are raised immediately without failover.

    Usage:
        primary = GLMProvider(provider="glm")
        secondary = GLMProvider(provider="openai")
        provider = FailoverProvider([primary, secondary])
        stream = provider.chat(messages, tools=tools)
    """

    def __init__(self, providers: list[GLMProvider]):
        if not providers:
            raise ValueError("At least one provider is required")
        self.providers = providers
        # Expose the first provider's model as the "active" model
        self.model = providers[0].model
        # Expose config attributes for /env — show first provider's values
        # with "_provider_name" set to "failover" to distinguish from single providers
        self._provider_name = "failover"
        self.api_key = providers[0].api_key
        self.base_url = providers[0].base_url
        self.max_tokens = providers[0].max_tokens
        self.temperature = providers[0].temperature
        self.top_p = providers[0].top_p
        self.reasoning_effort = providers[0].reasoning_effort

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        stream: bool = True,
    ) -> Any:
        """Try each provider in order until one succeeds.

        Raises APIError if all providers fail or if a non-retryable error occurs.
        """
        last_error: APIError | None = None

        for i, provider in enumerate(self.providers):
            try:
                # Propagate reasoning effort to each underlying provider
                provider.reasoning_effort = self.reasoning_effort
                result = provider.chat(messages=messages, tools=tools, stream=stream)
                # Update the active model reference
                self.model = provider.model
                return result
            except APIError as e:
                # Non-retryable errors (auth, bad_request) don't get failover
                if not e.retryable:
                    raise

                last_error = e
                # Log the failover attempt (provider name from model)
                if i < len(self.providers) - 1:
                    import sys
                    next_provider = self.providers[i + 1]
                    print(
                        f"\n  ⚠ Provider {provider.model} failed ({e.category}), "
                        f"falling back to {next_provider.model}...",
                        file=sys.stderr,
                    )

        # All providers exhausted
        raise APIError(
            f"All providers failed (tried {len(self.providers)}). Last error: {last_error}",
            category="retry_exhausted",
            retryable=False,
        )

    @staticmethod
    def parse_usage(response: Any) -> Usage:
        """Extract token usage — delegates to GLMProvider.parse_usage."""
        return GLMProvider.parse_usage(response)
