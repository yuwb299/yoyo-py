"""Test --continue flag: run initial prompt then enter interactive REPL."""

import io
from unittest.mock import patch, MagicMock

from src.repl import run_repl
from src.provider import GLMProvider, Usage


def test_continue_flag_in_main():
    """--continue should be accepted as a CLI argument."""
    from src.main import parse_args
    with patch("sys.argv", ["main", "-p", "hello", "--continue"]):
        args = parse_args()
    assert args.prompt == "hello"
    assert args.continue_repl is True


def test_no_continue_by_default():
    """Without --continue, the flag should be False."""
    from src.main import parse_args
    with patch("sys.argv", ["main", "-p", "hello"]):
        args = parse_args()
    assert args.continue_repl is False


def test_continue_without_prompt_is_noop():
    """--continue without -p should have no effect (just starts REPL normally)."""
    from src.main import parse_args
    with patch("sys.argv", ["main", "--continue"]):
        args = parse_args()
    assert args.prompt is None
    assert args.continue_repl is True
