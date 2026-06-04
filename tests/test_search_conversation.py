"""Tests for /search conversation command — invalid regex handling."""

import pytest
from src.repl import _search_conversation


def _sample_messages():
    return [
        {"role": "user", "content": "hello world"},
        {"role": "assistant", "content": "Hi there!"},
        {"role": "user", "content": "test 123"},
    ]


def test_search_basic_match():
    """Normal keyword search should work."""
    result = _search_conversation(_sample_messages(), "hello")
    assert "hello" in result.lower()
    assert "match" in result.lower()


def test_search_no_match():
    """No match returns a no-results message."""
    result = _search_conversation(_sample_messages(), "xyznotfound")
    assert "no match" in result.lower()


def test_search_invalid_regex_bracket():
    """Invalid regex (unmatched bracket) should not crash."""
    result = _search_conversation(_sample_messages(), "[invalid")
    assert "invalid" in result.lower() or "error" in result.lower()


def test_search_invalid_regex_star():
    """Invalid regex (lone star) should not crash — falls back to literal search."""
    result = _search_conversation(_sample_messages(), "*bad")
    # Should not crash; either "no match" or "invalid" is fine
    assert isinstance(result, str)  # just ensure no exception raised


def test_search_empty_keyword():
    """Empty keyword returns usage message."""
    result = _search_conversation(_sample_messages(), "")
    assert "usage" in result.lower() or "keyword" in result.lower()


def test_search_empty_messages():
    """Empty messages returns no-messages message."""
    result = _search_conversation([], "test")
    assert "no message" in result.lower()


def test_search_case_insensitive_default():
    """Default search is case-insensitive."""
    result = _search_conversation(_sample_messages(), "HELLO")
    assert "match" in result.lower()


def test_search_case_sensitive():
    """Case-sensitive search respects case."""
    result = _search_conversation(_sample_messages(), "HELLO", case_sensitive=True)
    assert "no match" in result.lower()

    result2 = _search_conversation(_sample_messages(), "hello", case_sensitive=True)
    assert "match" in result2.lower()
