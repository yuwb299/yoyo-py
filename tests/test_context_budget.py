"""Tests for context window budget tracking and warnings."""

from src.repl import (
    _format_status_output,
    _get_model_context_window,
    _format_context_budget,
)
from src.provider import Usage


class TestModelContextWindow:
    """Test model context window size lookup."""

    def test_glm5_context_window(self):
        assert _get_model_context_window("glm-5.1") == 128000

    def test_gpt4o_context_window(self):
        assert _get_model_context_window("gpt-4o") == 128000

    def test_gpt4o_mini_context_window(self):
        assert _get_model_context_window("gpt-4o-mini") == 128000

    def test_deepseek_context_window(self):
        assert _get_model_context_window("deepseek-chat") == 64000

    def test_moonshot_8k_context_window(self):
        assert _get_model_context_window("moonshot-v1-8k") == 8192

    def test_moonshot_128k_context_window(self):
        assert _get_model_context_window("moonshot-v1-128k") == 131072

    def test_unknown_model_returns_default(self):
        # Unknown models should return a reasonable default
        result = _get_model_context_window("unknown-model-xyz")
        assert result == 128000  # Default fallback

    def test_versioned_model_matches_prefix(self):
        # gpt-4o-2024-05-13 should match gpt-4o prefix
        result = _get_model_context_window("gpt-4o-2024-05-13")
        assert result == 128000

    def test_glm4_context_window(self):
        assert _get_model_context_window("glm-4") == 128000

    def test_glm4_flash_context_window(self):
        assert _get_model_context_window("glm-4-flash") == 128000


class TestContextBudgetFormatting:
    """Test context budget display formatting."""

    def test_format_budget_normal_usage(self):
        # 50K tokens used out of 128K
        result = _format_context_budget(50000, 128000)
        assert "39%" in result
        assert "50,000" in result or "50000" in result
        assert "128,000" in result or "128000" in result

    def test_format_budget_high_usage(self):
        # 110K tokens used out of 128K (85.9%)
        result = _format_context_budget(110000, 128000)
        assert "85%" in result
        # Should include a warning indicator
        assert "⚠" in result or "!" in result or "high" in result.lower()

    def test_format_budget_low_usage(self):
        # 10K tokens used out of 128K (~7.8%)
        result = _format_context_budget(10000, 128000)
        assert "7%" in result

    def test_format_budget_zero_usage(self):
        result = _format_context_budget(0, 128000)
        assert "0%" in result

    def test_format_budget_exactly_80_percent(self):
        # Exactly at the warning threshold
        result = _format_context_budget(102400, 128000)
        assert "80%" in result


class TestStatusWithContextBudget:
    """Test that /status shows context budget information."""

    def test_status_shows_budget_percentage(self):
        messages = [
            {"role": "system", "content": "test"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        usage = Usage(input_tokens=100, output_tokens=50)
        result = _format_status_output(
            model="glm-5.1",
            cwd="/tmp",
            messages=messages,
            usage=usage,
            skills_count=0,
            context_tokens=50000,
        )
        # Should show budget percentage
        assert "39%" in result or "context" in result.lower()
        assert "128" in result  # Should reference the model's context window
