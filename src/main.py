#!/usr/bin/env python3
"""yoyo-py — a self-evolving coding agent built with Python + GLM 5.

Usage:
    GLM_API_KEY=*** python -m src.main
    GLM_API_KEY=*** python -m src.main --skills ./skills
    python -m src.main -p "explain this codebase"
    echo "write a README" | python -m src.main
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv

# Load .env before anything else
load_dotenv()

from .provider import GLMProvider
from .repl import run_repl
from . import __version__


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="yoyo-py — a self-evolving coding agent (Python + GLM 5)",
    )
    parser.add_argument(
        "-p", "--prompt",
        help="Run a single prompt and exit",
    )
    parser.add_argument(
        "--skills",
        nargs="*",
        default=["./skills"],
        help="Skill directories to load (default: ./skills)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model name (default: from GLM_MODEL env or glm-5.1)",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="API base URL (default: from GLM_BASE_URL env)",
    )
    parser.add_argument(
        "--provider",
        default=None,
        choices=None,
        help="Provider preset: glm, openai, deepseek, moonshot, zhipu, anthropic, google",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Auto-approve all destructive tool calls (bash, write_file, edit_file)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="Max tokens in LLM response (default: API default)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="Sampling temperature 0.0-2.0 (default: API default)",
    )
    parser.add_argument(
        "--top-p",
        type=float,
        default=None,
        help="Nucleus sampling threshold 0.0-1.0 (default: API default)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--think",
        default=None,
        choices=["low", "medium", "high"],
        help="Set reasoning effort at startup (low/medium/high)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume last auto-saved session on startup",
    )
    parser.add_argument(
        "--cwd",
        default=None,
        help="Change working directory before starting (useful for scripting)",
    )
    parser.add_argument(
        "--list-providers",
        action="store_true",
        help="List available provider presets and exit",
    )
    return parser.parse_args()


def _print_providers() -> None:
    """Print available provider presets with their env vars and default models."""
    from .provider import PROVIDER_PRESETS

    print("Available provider presets:")
    print()
    for name, config in sorted(PROVIDER_PRESETS.items()):
        print(f"  {name:12} env: {config['env_key']:20} model: {config['default_model']}")
    print()
    print("Usage: --provider <name>")
    print("Set the API key via environment variable or .env file.")


def main() -> None:
    args = parse_args()

    # Change working directory early so provider, skills, etc. all resolve correctly
    if args.cwd:
        cwd = os.path.abspath(args.cwd)
        if not os.path.isdir(cwd):
            print(f"Error: --cwd directory not found: {cwd}", file=sys.stderr)
            sys.exit(1)
        os.chdir(cwd)

    if args.list_providers:
        _print_providers()
        sys.exit(0)

    try:
        provider = GLMProvider(
            model=args.model,
            base_url=args.base_url,
            provider=args.provider,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            top_p=args.top_p,
        )
        # Set reasoning effort from CLI flag
        if args.think:
            provider.reasoning_effort = args.think
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Set the appropriate API key in .env or environment.", file=sys.stderr)
        sys.exit(1)

    # Check for piped stdin
    pipe_input = None
    if not sys.stdin.isatty():
        pipe_input = sys.stdin.read().strip()
        # Reopen tty for interactive use; /dev/tty may not exist on Windows/CI
        try:
            sys.stdin = open("/dev/tty")
        except OSError:
            # Fall back to original stdin (e.g. in CI or Windows environments)
            pass

    asyncio.run(
        run_repl(
            provider=provider,
            skill_dirs=args.skills,
            verbose=args.verbose,
            initial_prompt=args.prompt,
            pipe_input=pipe_input,
            auto_approve=args.yes,
            resume=args.resume,
        )
    )


if __name__ == "__main__":
    main()
