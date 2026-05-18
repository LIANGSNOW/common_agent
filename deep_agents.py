"""CLI entrypoint for the domain-neutral common agent.

Run with:
    python deep_agents.py
"""

import sys

from src.cli_common_agent import run_from_stdin, run_once, run_repl


def main() -> None:
    if sys.stdin.isatty():
        run_repl()
    else:
        run_from_stdin(sys.stdin)


if __name__ == "__main__":
    main()
