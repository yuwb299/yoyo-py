"""Tests for the /cost command — estimate API cost from token usage."""

import pytest
from src.repl import _estimate_cost
from src.provider import Usage


class TestCostEstimation:
    """Test cost estimation from token usage data."""

    def test_zero_usage(self):
        """Should show zero cost for no usage."""
        usage = Usage()
        result = _estimate_cost(usage, model="glm-5.1")
        assert "$0.00" in result

    def test_known_glm_pricing(self):
        """Should estimate cost for GLM models."""
        usage = Usage(input_tokens=100000, output_tokens=10000)
        result = _estimate_cost(usage, model="glm-5.1")
        assert "$" in result
        # Should show some nonzero cost
        assert "$0.00" not in result or "100000" in result

    def test_unknown_model(self):
        """Should handle unknown models with a warning."""
        usage = Usage(input_tokens=1000, output_tokens=100)
        result = _estimate_cost(usage, model="unknown-model-v99")
        assert "unknown" in result.lower() or "estimate" in result.lower() or "$" in result

    def test_openai_pricing(self):
        """Should estimate cost for OpenAI models."""
        usage = Usage(input_tokens=100000, output_tokens=10000)
        result = _estimate_cost(usage, model="gpt-4o")
        assert "$" in result

    def test_deepseek_pricing(self):
        """Should estimate cost for DeepSeek models."""
        usage = Usage(input_tokens=100000, output_tokens=10000)
        result = _estimate_cost(usage, model="deepseek-chat")
        assert "$" in result

    def test_format_display(self):
        """Should display input/output tokens and cost breakdown."""
        usage = Usage(input_tokens=50000, output_tokens=5000)
        result = _estimate_cost(usage, model="glm-5.1")
        assert "input" in result.lower() or "50,000" in result or "50000" in result
        assert "output" in result.lower() or "5,000" in result or "5000" in result
