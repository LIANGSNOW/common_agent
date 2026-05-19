import sys
from datetime import datetime
from pathlib import Path
from typing import TextIO

from langchain_core.messages import HumanMessage

from src.agents.common import create_common_agent


class ChatHistoryWriter:
    def __init__(
        self,
        history_dir: str | Path = "history/common-agent",
        session_name: str | None = None,
    ):
        self.history_dir = Path(history_dir)
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.session_name = session_name or datetime.now().strftime("%Y%m%d-%H%M%S")
        self.path = self.history_dir / f"{self.session_name}.md"
        if not self.path.exists():
            self.path.write_text(f"# Common Agent Session\n\nSession: {self.session_name}\n\n", encoding="utf-8")

    def write_turn(self, user_input: str, result: dict) -> None:
        parts = ["## User\n\n", user_input, "\n\n## Agent\n\n"]
        for message in result.get("messages", []):
            parts.append(_message_for_review(message))
            parts.append("\n\n")
        with self.path.open("a", encoding="utf-8") as file:
            file.write("".join(parts))


def _message_for_review(message) -> str:
    pretty_repr = getattr(message, "pretty_repr", None)
    if callable(pretty_repr):
        return str(pretty_repr())
    return str(getattr(message, "content", message))


def _message_content(message) -> str:
    return str(getattr(message, "content", message))


def _print_message(message, output_fn=None) -> None:
    if output_fn is not None:
        output_fn(_message_content(message))
        return

    pretty_print = getattr(message, "pretty_print", None)
    if callable(pretty_print):
        pretty_print()
    else:
        print(_message_content(message))


def _stream_values(agent, user_input: str):
    yield from agent.stream(
        {"messages": [HumanMessage(content=user_input)]},
        stream_mode="values",
    )


def run_once(user_input: str, agent=None, history_writer: ChatHistoryWriter | None = None, output_fn=None):
    selected_agent = agent or create_common_agent()
    final_result: dict = {"messages": []}
    printed_count = 0

    for state in _stream_values(selected_agent, user_input):
        final_result = state
        messages = state.get("messages", [])
        for message in messages[printed_count:]:
            _print_message(message, output_fn=output_fn)
        printed_count = len(messages)

    if history_writer is not None:
        history_writer.write_turn(user_input, final_result)

    return final_result


def run_from_stdin(stdin: TextIO = sys.stdin, history_writer: ChatHistoryWriter | None = None, output_fn=None):
    user_input = stdin.read()
    writer = history_writer or ChatHistoryWriter()
    result = run_once(user_input, history_writer=writer, output_fn=output_fn)
    if output_fn is not None:
        output_fn(f"\nSaved conversation to: {writer.path}")
    else:
        print(f"\nSaved conversation to: {writer.path}")
    return result


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
    history_writer = ChatHistoryWriter()
    print("Common Agent CLI. Type 'exit' or 'quit' to stop. Type '/multi' for multiline input.")
    print(f"Saving conversation to: {history_writer.path}")
    while True:
        user_input = input("\n> ").strip()
        if user_input.lower() in {"exit", "quit"}:
            break
        if user_input == "/multi":
            user_input = collect_multiline_input()
        if not user_input:
            continue

        run_once(user_input, agent=agent, history_writer=history_writer)


if __name__ == "__main__":
    run_repl()
