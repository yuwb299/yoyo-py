"""GLM 5 API provider — OpenAI-compatible interface for Zhipu AI."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI


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
    elif isinstance(error, APIConnectionError):
        return APIError(
            f"Connection error: {error}",
            category="connection",
            retryable=True,
        )
    elif isinstance(error, APITimeoutError):
        return APIError(
            f"Request timed out: {error}",
            category="timeout",
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
    ):
        self.api_key = api_key or os.getenv("GLM_API_KEY", "")
        self.base_url = base_url or os.getenv(
            "GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"
        )
        self.model = model or os.getenv("GLM_MODEL", "glm-5.1")

        if not self.api_key:
            raise ValueError(
                "GLM_API_KEY is required. Set it in .env or pass to constructor."
            )

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
