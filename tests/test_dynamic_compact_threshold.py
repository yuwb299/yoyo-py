"""Tests for dynamic compact_threshold based on model context window.

The compact threshold should adapt to the model's context window:
- Small models (8K) → compact early (~4,920 tokens)
- Standard models (128K) → compact at ~76,800 tokens
- Large models (1M+) → compact at ~600,000+ tokens

This prevents two failure modes:
1. Compact triggers too early on large-context models, wasting context
2. Compact never triggers on small-context models, causing API errors
"""

import pytest
from src.agent import Agent, AgentState
from src.provider import get_model_context_window, MODEL_CONTEXT_WINDOWS, DEFAULT_CONTEXT_WINDOW


class TestDynamicCompactThreshold:
    """Test that compact_threshold adapts to the model's context window."""

    def test_compact_threshold_is_60_percent_of_context_window(self):
        """Compact threshold should be ~60% of model's context window."""
        for model, ctx_window in MODEL_CONTEXT_WINDOWS.items():
            threshold = Agent._compute_compact_threshold(model)
            expected = int(ctx_window * 0.6)
            assert threshold == expected, (
                f"Model {model}: threshold {threshold} != {expected} (60% of {ctx_window})"
            )

    def test_compact_threshold_unknown_model_uses_default(self):
        """Unknown models should use default context window for threshold."""
        threshold = Agent._compute_compact_threshold("unknown-model-xyz")
        expected = int(DEFAULT_CONTEXT_WINDOW * 0.6)
        assert threshold == expected

    def test_compact_threshold_small_model(self):
        """Small context models should compact early."""
        # moonshot-v1-8k has 8K context
        threshold = Agent._compute_compact_threshold("moonshot-v1-8k")
        assert threshold == int(8192 * 0.6)
        assert threshold < 8000  # Much less than old hardcoded 80K

    def test_compact_threshold_large_model(self):
        """Large context models should compact much later."""
        # gemini-2.5-pro has 1M context
        threshold = Agent._compute_compact_threshold("gemini-2.5-pro")
        assert threshold == int(1048576 * 0.6)
        assert threshold > 80000  # Much more than old hardcoded 80K

    def test_compact_threshold_updates_on_model_change(self):
        """When model changes, compact_threshold should update accordingly."""
        from unittest.mock import MagicMock
        provider = MagicMock()
        provider.model = "glm-5.1"
        agent = Agent(
            provider=provider,
            system_prompt="test",
            tools=[],
            tool_schemas=[],
        )
        # Initial threshold based on glm-5.1 (128K context)
        initial = agent.state.compact_threshold
        assert initial == int(128000 * 0.6)

        # Change model to moonshot-v1-8k (8K context)
        provider.model = "moonshot-v1-8k"
        # _update_compact_threshold should adapt
        agent._update_compact_threshold()
        assert agent.state.compact_threshold == int(8192 * 0.6)
        assert agent.state.compact_threshold < initial

    def test_state_default_compact_threshold_is_reasonable(self):
        """Default AgentState.compact_threshold should be a sensible fallback."""
        state = AgentState()
        # Should be 60% of default context window (128K)
        assert state.compact_threshold == int(128000 * 0.6)

    def test_prefix_model_matching(self):
        """Models with version suffixes should match their base model."""
        # gpt-4o-2024-05-13 should match gpt-4o's context
        threshold = Agent._compute_compact_threshold("gpt-4o-2024-05-13")
        expected = int(128000 * 0.6)
        assert threshold == expected

    def test_get_model_context_window_in_provider(self):
        """Verify get_model_context_window works for known models."""
        assert get_model_context_window("glm-5.1") == 128000
        assert get_model_context_window("gemini-2.5-pro") == 1048576
        assert get_model_context_window("moonshot-v1-8k") == 8192
        # Prefix match
        assert get_model_context_window("gpt-4o-2024-05-13") == 128000
        # Unknown model
        assert get_model_context_window("totally-unknown") == DEFAULT_CONTEXT_WINDOW
