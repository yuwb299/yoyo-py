"""Tests for tab completion of /model and /provider commands."""

from src.repl import _complete_model_names, _complete_provider_names


class TestModelTabCompletion:
    """Test that /model tab-completes known model names."""

    def test_complete_glm_prefix(self):
        """Typing 'glm' should complete to glm-4, glm-4-flash, glm-4-plus, glm-5, glm-5.1."""
        matches = _complete_model_names("glm")
        assert "glm-5" in matches
        assert "glm-5.1" in matches
        assert "glm-4-plus" in matches

    def test_complete_exact_match(self):
        """Exact model name should return just that name."""
        matches = _complete_model_names("gpt-4o")
        assert "gpt-4o" in matches
        assert "gpt-4o-mini" in matches

    def test_complete_no_match(self):
        """Unknown prefix returns empty list."""
        matches = _complete_model_names("zzz-nonexistent")
        assert matches == []

    def test_complete_empty_returns_all(self):
        """Empty prefix returns all known models."""
        matches = _complete_model_names("")
        assert len(matches) > 20  # We have many models

    def test_complete_gemini(self):
        """Gemini models should complete."""
        matches = _complete_model_names("gemini")
        assert "gemini-2.5-pro" in matches
        assert "gemini-2.5-flash" in matches

    def test_complete_moonshot(self):
        """Moonshot models should complete."""
        matches = _complete_model_names("moonshot")
        assert "moonshot-v1-8k" in matches
        assert "moonshot-v1-128k" in matches


class TestProviderTabCompletion:
    """Test that /provider tab-completes provider preset names."""

    def test_complete_all_providers(self):
        """Empty prefix returns all provider names."""
        matches = _complete_provider_names("")
        assert "glm" in matches
        assert "openai" in matches
        assert "deepseek" in matches

    def test_complete_g(self):
        """'g' should match google and glm."""
        matches = _complete_provider_names("g")
        assert "glm" in matches
        assert "google" in matches

    def test_complete_exact(self):
        """Exact provider name returns just that."""
        matches = _complete_provider_names("openai")
        assert "openai" in matches

    def test_complete_no_match(self):
        """Unknown prefix returns empty."""
        matches = _complete_provider_names("zzz")
        assert matches == []

    def test_all_results_sorted(self):
        """Results should be sorted alphabetically."""
        matches = _complete_provider_names("")
        assert matches == sorted(matches)
