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
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        provider = GLMProvider(
            model=args.model,
            base_url=args.base_url,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Set GLM_API_KEY in .env or environment.", file=sys.stderr)
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
        )
    )


if __name__ == "__main__":
    main()
