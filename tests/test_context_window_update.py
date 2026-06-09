"""Tests for updated model context window table.

Validates that newer models (GPT-4.1, o3, o4-mini, Claude, Gemini, etc.)
have entries in the context window table so budget warnings work correctly.
"""

import pytest
from src.repl import _get_model_context_window, _MODEL_CONTEXT_WINDOWS


class TestContextWindowTable:
    """Test that context window lookup works for all supported providers."""

    # ── New OpenAI models (2025) ──────────────────────────────────────

    def test_gpt41_context_window(self):
        """GPT-4.1 has a 1M token context window."""
        assert _get_model_context_window("gpt-4.1") == 1047576

    def test_gpt41_mini_context_window(self):
        """GPT-4.1 mini has a 1M token context window."""
        assert _get_model_context_window("gpt-4.1-mini") == 1047576

    def test_gpt41_nano_context_window(self):
        """GPT-4.1 nano has a 1M token context window."""
        assert _get_model_context_window("gpt-4.1-nano") == 1047576

    def test_o3_context_window(self):
        """o3 has a 200K token context window."""
        assert _get_model_context_window("o3") == 200000

    def test_o3_mini_context_window(self):
        """o3-mini has a 200K token context window."""
        assert _get_model_context_window("o3-mini") == 200000

    def test_o4_mini_context_window(self):
        """o4-mini has a 200K token context window."""
        assert _get_model_context_window("o4-mini") == 200000

    # ── Claude models ─────────────────────────────────────────────────

    def test_claude_sonnet_4_context_window(self):
        """Claude Sonnet 4 has a 200K context window."""
        assert _get_model_context_window("claude-sonnet-4-20250514") == 200000

    def test_claude_37_sonnet_context_window(self):
        """Claude 3.7 Sonnet has a 200K context window."""
        assert _get_model_context_window("claude-3-7-sonnet") == 200000

    # ── Gemini models ─────────────────────────────────────────────────

    def test_gemini_25_pro_context_window(self):
        """Gemini 2.5 Pro has a 1M context window."""
        assert _get_model_context_window("gemini-2.5-pro") == 1048576

    def test_gemini_25_flash_context_window(self):
        """Gemini 2.5 Flash has a 1M context window."""
        assert _get_model_context_window("gemini-2.5-flash") == 1048576

    # ── DeepSeek models ───────────────────────────────────────────────

    def test_deepseek_v3_context_window(self):
        """DeepSeek-V3 has a 128K context window."""
        assert _get_model_context_window("deepseek-v3") == 128000

    def test_deepseek_r1_context_window(self):
        """DeepSeek-R1 has a 128K context window."""
        assert _get_model_context_window("deepseek-r1") == 128000

    # ── Existing models still work ────────────────────────────────────

    def test_glm51_still_works(self):
        """GLM-5.1 context window should still resolve correctly."""
        assert _get_model_context_window("glm-5.1") == 128000

    def test_gpt4o_still_works(self):
        """GPT-4o context window should still resolve correctly."""
        assert _get_model_context_window("gpt-4o") == 128000

    def test_unknown_model_returns_default(self):
        """Unknown models should return the default context window."""
        from src.repl import _DEFAULT_CONTEXT_WINDOW
        result = _get_model_context_window("totally-unknown-model-xyz")
        assert result == _DEFAULT_CONTEXT_WINDOW

    # ── Prefix matching for versioned models ──────────────────────────

    def test_gpt41_versioned_model(self):
        """GPT-4.1 with version suffix should match the base entry."""
        # The model "gpt-4.1-2025-04-14" should match "gpt-4.1" via prefix
        assert _get_model_context_window("gpt-4.1-2025-04-14") == 1047576

    def test_claude_sonnet_4_versioned(self):
        """Claude Sonnet 4 should have a specific or prefix-matched entry."""
        result = _get_model_context_window("claude-sonnet-4-20250514")
        assert result >= 200000

    def test_o3_versioned_model(self):
        """o3 with version suffix should match via prefix."""
        assert _get_model_context_window("o3-2025-04-16") == 200000

    # ── Table consistency ─────────────────────────────────────────────

    def test_all_entries_positive(self):
        """Every model in the table should have a positive context window."""
        for model, window in _MODEL_CONTEXT_WINDOWS.items():
            assert window > 0, f"{model} has non-positive context window: {window}"

    def test_all_entries_reasonable_upper_bound(self):
        """No context window should exceed 10M tokens (sanity check)."""
        for model, window in _MODEL_CONTEXT_WINDOWS.items():
            assert window <= 10_000_000, f"{model} has unreasonable context window: {window}"
