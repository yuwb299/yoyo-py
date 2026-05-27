"""Test --list-providers CLI flag."""

import pytest
from unittest.mock import patch
import sys


def test_list_providers_output():
    """--list-providers should print available provider presets and exit."""
    from src.main import parse_args
    import io
    from contextlib import redirect_stdout

    # Test that --list-providers is accepted
    with patch("sys.argv", ["main.py", "--list-providers"]):
        args = parse_args()
        assert args.list_providers is True


def test_list_providers_shows_all_presets():
    """The output should include all provider preset names."""
    from src.provider import PROVIDER_PRESETS
    from src.main import _print_providers
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        _print_providers()

    output = buf.getvalue()
    for name in PROVIDER_PRESETS:
        assert name in output, f"Provider '{name}' not in output"


def test_list_providers_shows_env_keys():
    """The output should show which env var each provider uses."""
    from src.main import _print_providers
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        _print_providers()

    output = buf.getvalue()
    assert "GLM_API_KEY" in output
    assert "OPENAI_API_KEY" in output
    assert "DEEPSEEK_API_KEY" in output
