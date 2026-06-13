"""Tests for generation parameter validation.

temperature (0.0-2.0), top_p (0.0-1.0), and max_tokens (>=1) are clamped
to valid ranges in the GLMProvider constructor. Without this, the API
rejects out-of-range values with an opaque bad_request error that the
agent surfaces as 'API rejected the request' — unhelpful.
"""

import os

import pytest

# Ensure an API key exists so construction doesn't fail on that check
os.environ.setdefault("GLM_API_KEY", "test-key")

from src.provider import GLMProvider


def test_temperature_clamped_to_range():
    p = GLMProvider(temperature=5.0)
    assert 0.0 <= p.temperature <= 2.0
    assert p.temperature == 2.0

    p = GLMProvider(temperature=-1.0)
    assert p.temperature == 0.0

    p = GLMProvider(temperature=0.7)
    assert p.temperature == 0.7  # in-range unchanged


def test_top_p_clamped_to_range():
    p = GLMProvider(top_p=1.5)
    assert 0.0 <= p.top_p <= 1.0
    assert p.top_p == 1.0

    p = GLMProvider(top_p=-0.5)
    assert p.top_p == 0.0

    p = GLMProvider(top_p=0.9)
    assert p.top_p == 0.9  # in-range unchanged


def test_max_tokens_clamped_positive():
    p = GLMProvider(max_tokens=-10)
    assert p.max_tokens is None or p.max_tokens >= 1

    p = GLMProvider(max_tokens=0)
    assert p.max_tokens is None or p.max_tokens >= 1

    p = GLMProvider(max_tokens=1024)
    assert p.max_tokens == 1024


def test_valid_values_unchanged():
    p = GLMProvider(temperature=1.0, top_p=0.5, max_tokens=512)
    assert p.temperature == 1.0
    assert p.top_p == 0.5
    assert p.max_tokens == 512


def test_none_values_unchanged():
    """None means 'use API default' — must stay None."""
    p = GLMProvider()
    assert p.temperature is None
    assert p.top_p is None
    assert p.max_tokens is None
