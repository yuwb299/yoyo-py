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

# ── Model context windows ──────────────────────────────────────────────
# Context window sizes in tokens for known models.
# Used for budget warnings and adaptive compact thresholds.
# Shared between provider.py, agent.py, and repl.py.

MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    # GLM models (Zhipu AI)
    "glm-5": 128000,
    "glm-5.1": 128000,
    "glm-4-plus": 128000,
    "glm-4": 128000,
    "glm-4-flash": 128000,
    # OpenAI models (GPT-4.x)
    "gpt-4.1": 1047576,        # 1M context (2025-04)
    "gpt-4.1-mini": 1047576,   # 1M context (2025-04)
    "gpt-4.1-nano": 1047576,   # 1M context (2025-04)
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4-turbo": 128000,
    # OpenAI models (o-series reasoning)
    "o1": 200000,
    "o1-mini": 128000,
    "o3": 200000,              # 200K context (2025-04)
    "o3-mini": 200000,         # 200K context (2025-01)
    "o4-mini": 200000,         # 200K context (2025-04)
    # Anthropic models (Claude)
    "claude-opus-4": 200000,   # 200K context (2025-05)
    "claude-sonnet-4": 200000, # 200K context (2025-05)
    "claude-3-7-sonnet": 200000,
    "claude-3-5-sonnet": 200000,
    "claude-3-opus": 200000,
    "claude-3-haiku": 200000,
    # Google models (Gemini)
    "gemini-2.5-pro": 1048576,  # 1M context (2025-03)
    "gemini-2.5-flash": 1048576, # 1M context (2025-04)
    "gemini-2.0-flash": 1048576, # 1M context
    # DeepSeek models
    "deepseek-chat": 64000,
    "deepseek-reasoner": 64000,
    "deepseek-v3": 128000,     # V3 expanded to 128K
    "deepseek-r1": 128000,     # R1 expanded to 128K
    # Moonshot models
    "moonshot-v1-8k": 8192,
    "moonshot-v1-32k": 32768,
    "moonshot-v1-128k": 131072,
}

DEFAULT_CONTEXT_WINDOW = 128000


def get_model_context_window(model: str) -> int:
    """Get the context window size for a model.

    Handles version suffixes by trying prefix matching.
    E.g. 'gpt-4o-2024-05-13' matches 'gpt-4o'.

    Returns the context window in tokens, or a default if unknown.
    """
    if model in MODEL_CONTEXT_WINDOWS:
        return MODEL_CONTEXT_WINDOWS[model]

    # Try prefix matching: longer prefixes first for specificity
    for prefix in sorted(MODEL_CONTEXT_WINDOWS.keys(), key=len, reverse=True):
        if model.startswith(prefix):
            return MODEL_CONTEXT_WINDOWS[prefix]

    return DEFAULT_CONTEXT_WINDOW


def format_context_size(tokens: int) -> str:
    """Format a context window size as a human-readable string.

    Returns '1.0M' for million-token models, '128K' for smaller ones.
    Shared between main.py (--list-models) and repl.py (/models).
    """
    if tokens >= 1_000_000:
        return f"{tokens / 1_000_000:.1f}M"
    return f"{tokens // 1000}K"


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
    "anthropic": {
        # Anthropic doesn't expose a native OpenAI-compatible endpoint,
        # but many proxies (LiteLLM, OpenRouter, etc.) do. Users can
        # override --base-url for their specific proxy.
        "base_url": "https://api.anthropic.com/v1",
        "env_key": "ANTHROPIC_API_KEY",
        "default_model": "claude-sonnet-4-20250514",
    },
    "google": {
        # Google Gemini via OpenAI-compatible endpoint.
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "env_key": "GOOGLE_API_KEY",
        "default_model": "gemini-2.5-pro",
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
