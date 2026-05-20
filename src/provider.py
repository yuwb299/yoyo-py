"""GLM 5 API provider — OpenAI-compatible interface for Zhipu AI."""

from __future__ import annotations

import os
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


class GLMProvider:
    """GLM 5 provider via OpenAI-compatible API."""

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
        """Send a chat completion request.

        Returns a stream if stream=True, else a completion object.
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        return self.client.chat.completions.create(**kwargs)

    @staticmethod
    def parse_usage(response: Any) -> Usage:
        """Extract token usage from a response chunk or final response."""
        if hasattr(response, "usage") and response.usage:
            return Usage(
                input_tokens=getattr(response.usage, "prompt_tokens", 0) or 0,
                output_tokens=getattr(response.usage, "completion_tokens", 0) or 0,
            )
        return Usage()
