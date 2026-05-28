"""Tests for /config REPL command — view and set generation params at runtime."""

import pytest
from unittest.mock import MagicMock

from src.repl import _handle_config_command


def test_config_show_all():
    """Showing config lists all generation params."""
    output, updates = _handle_config_command(
        args_str="",
        temperature=0.7,
        max_tokens=4096,
        top_p=0.9,
        model="glm-5.1",
    )
    assert "temperature" in output.lower()
    assert "max_tokens" in output.lower()
    assert "top_p" in output.lower()
    assert "0.7" in output
    assert "4096" in output
    assert updates == {}


def test_config_show_defaults():
    """Showing config when params are None indicates defaults."""
    output, updates = _handle_config_command(
        args_str="",
        temperature=None,
        max_tokens=None,
        top_p=None,
        model="glm-5.1",
    )
    assert "default" in output.lower() or "none" in output.lower()
    assert updates == {}


def test_config_set_temperature():
    """Setting temperature returns the update."""
    output, updates = _handle_config_command(
        args_str="temperature 0.5",
        temperature=None,
        max_tokens=None,
        top_p=None,
        model="glm-5.1",
    )
    assert "0.5" in output
    assert updates == {"temperature": 0.5}


def test_config_set_max_tokens():
    """Setting max_tokens returns the update."""
    output, updates = _handle_config_command(
        args_str="max_tokens 2048",
        temperature=None,
        max_tokens=None,
        top_p=None,
        model="glm-5.1",
    )
    assert "2048" in output
    assert updates == {"max_tokens": 2048}


def test_config_set_top_p():
    """Setting top_p returns the update."""
    output, updates = _handle_config_command(
        args_str="top_p 0.95",
        temperature=None,
        max_tokens=None,
        top_p=None,
        model="glm-5.1",
    )
    assert "0.95" in output
    assert updates == {"top_p": 0.95}


def test_config_invalid_param():
    """Setting an unknown param returns an error."""
    output, updates = _handle_config_command(
        args_str="foobar 123",
        temperature=None,
        max_tokens=None,
        top_p=None,
        model="glm-5.1",
    )
    assert "unknown" in output.lower() or "usage" in output.lower()
    assert updates == {}


def test_config_invalid_value():
    """Setting a param to a non-numeric value returns an error."""
    output, updates = _handle_config_command(
        args_str="temperature abc",
        temperature=None,
        max_tokens=None,
        top_p=None,
        model="glm-5.1",
    )
    assert "invalid" in output.lower() or "number" in output.lower()
    assert updates == {}


def test_config_model_in_output():
    """Config output includes the current model."""
    output, updates = _handle_config_command(
        args_str="",
        temperature=None,
        max_tokens=None,
        top_p=None,
        model="glm-5.1",
    )
    assert "glm-5.1" in output
    assert updates == {}


def test_config_temperature_out_of_range():
    """Temperature above 2.0 is rejected."""
    output, updates = _handle_config_command(
        args_str="temperature 5.0",
        temperature=None,
        max_tokens=None,
        top_p=None,
        model="glm-5.1",
    )
    assert "0.0" in output and "2.0" in output
    assert updates == {}


def test_config_max_tokens_zero_rejected():
    """max_tokens of 0 is rejected."""
    output, updates = _handle_config_command(
        args_str="max_tokens 0",
        temperature=None,
        max_tokens=None,
        top_p=None,
        model="glm-5.1",
    )
    assert "positive" in output.lower()
    assert updates == {}
