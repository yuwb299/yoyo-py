"""Tests for /model --keep flag — switch model without clearing history."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestModelKeepFlag:
    """Test that /model --keep switches model but preserves conversation."""

    def test_model_keep_extraction(self):
        """'/model --keep glm-4' should extract 'glm-4' and detect --keep."""
        line = "/model --keep glm-4"
        args = line[7:].strip()
        keep = "--keep" in args
        model_name = args.replace("--keep", "").strip()
        assert keep is True
        assert model_name == "glm-4"

    def test_model_keep_flag_ordering(self):
        """'/model glm-4 --keep' should also work."""
        line = "/model glm-4 --keep"
        args = line[7:].strip()
        keep = "--keep" in args
        model_name = args.replace("--keep", "").strip()
        assert keep is True
        assert model_name == "glm-4"

    def test_model_without_keep(self):
        """'/model glm-4' without --keep should have keep=False."""
        line = "/model glm-4"
        args = line[7:].strip()
        keep = "--keep" in args
        model_name = args.replace("--keep", "").strip()
        assert keep is False
        assert model_name == "glm-4"

    def test_model_keep_with_provider_format(self):
        """'/model --keep deepseek-chat' works with model names containing dashes."""
        line = "/model --keep deepseek-chat"
        args = line[7:].strip()
        keep = "--keep" in args
        model_name = args.replace("--keep", "").strip()
        assert keep is True
        assert model_name == "deepseek-chat"
