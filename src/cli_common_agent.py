import sys
from typing import TextIO

from langchain_core.messages import HumanMessage

from src.agents.common import create_common_agent


def _print_messages(result: dict) -> None:
    for message in result.get("messages", []):
        message.pretty_print()


def run_once(user_input: str, agent=None):
    selected_agent = agent or create_common_agent()
    result = selected_agent.invoke({"messages": [HumanMessage(content=user_input)]})
    _print_messages(result)
    return result


def run_from_stdin(stdin: TextIO = sys.stdin):
    user_input = stdin.read()
    return run_once(user_input)


def collect_multiline_input(input_fn=input, output_fn=print, terminator: str = "/end") -> str:
    output_fn(f"Paste your request. Finish with a single line containing {terminator}.")
    lines: list[str] = []
    while True:
        line = input_fn("")
        if line == terminator:
            break
        lines.append(line)
    return "\n".join(lines)


def run_repl() -> None:
    agent = create_common_agent()
    print("Common Agent CLI. Type 'exit' or 'quit' to stop. Type '/multi' for multiline input.")
    while True:
        user_input = input("\n> ").strip()
        if user_input.lower() in {"exit", "quit"}:
            break
        if user_input == "/multi":
            user_input = collect_multiline_input()
        if not user_input:
            continue

        run_once(user_input, agent=agent)


if __name__ == "__main__":
    run_repl()
