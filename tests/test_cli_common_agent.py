import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage

from src.cli_common_agent import (
    ChatHistoryWriter,
    collect_multiline_input,
    run_from_stdin,
    run_once,
)


class FakeMessage:
    def __init__(self, content="fake response"):
        self.content = content
        self.pretty_print_called = False

    def pretty_print(self):
        self.pretty_print_called = True


class FakeAgent:
    def __init__(self, message):
        self.message = message
        self.planner_message = FakeMessage("planner")
        self.received_input = None

    def invoke(self, agent_input):
        self.received_input = agent_input
        return {"messages": [self.message]}

    def stream(self, agent_input, stream_mode="values"):
        self.received_input = agent_input
        yield {"messages": [self.planner_message]}
        yield {"messages": [self.planner_message, self.message]}


class CliCommonAgentTests(unittest.TestCase):
    def test_run_once_invokes_agent_with_human_message_and_prints_result(self):
        message = FakeMessage()
        fake_agent = FakeAgent(message)
        printed: list[str] = []

        with patch("src.cli_common_agent.create_common_agent", return_value=fake_agent):
            result = run_once("hello", output_fn=lambda text: printed.append(text))

        sent_message = fake_agent.received_input["messages"][0]
        self.assertIsInstance(sent_message, HumanMessage)
        self.assertEqual(sent_message.content, "hello")
        self.assertEqual(printed, ["planner", "fake response"])
        self.assertEqual(result["messages"][-1], message)

    def test_run_once_streams_new_messages_without_reprinting_old_messages(self):
        message = FakeMessage("final")
        fake_agent = FakeAgent(message)
        printed: list[str] = []

        result = run_once(
            "hello",
            agent=fake_agent,
            output_fn=lambda text: printed.append(text),
        )

        self.assertEqual(printed, ["planner", "final"])
        self.assertEqual(result["messages"][-1].content, "final")

    def test_run_once_uses_pretty_print_by_default(self):
        message = FakeMessage("final")
        fake_agent = FakeAgent(message)

        result = run_once("hello", agent=fake_agent)

        planner_message = result["messages"][0]
        self.assertTrue(planner_message.pretty_print_called)
        self.assertTrue(message.pretty_print_called)

    def test_run_from_stdin_treats_all_text_as_one_request(self):
        message = FakeMessage()
        fake_agent = FakeAgent(message)
        stdin = io.StringIO("第一行\n\n第二行\n第三行\n")
        printed: list[str] = []

        with tempfile.TemporaryDirectory() as tmpdir:
            writer = ChatHistoryWriter(history_dir=Path(tmpdir), session_name="stdin-test")
            with patch("src.cli_common_agent.create_common_agent", return_value=fake_agent):
                result = run_from_stdin(stdin, history_writer=writer, output_fn=lambda text: printed.append(text))

        sent_message = fake_agent.received_input["messages"][0]
        self.assertEqual(sent_message.content, "第一行\n\n第二行\n第三行\n")
        self.assertIn("fake response", printed)
        self.assertEqual(result["messages"][-1], message)

    def test_collect_multiline_input_until_end_marker(self):
        lines = iter(["第一行", "", "第二行", "/end"])

        result = collect_multiline_input(input_fn=lambda _: next(lines), output_fn=lambda _: None)

        self.assertEqual(result, "第一行\n\n第二行")

    def test_history_writer_saves_user_and_agent_messages(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = ChatHistoryWriter(history_dir=Path(tmpdir), session_name="test-session")
            writer.write_turn(
                "用户问题",
                {"messages": [HumanMessage(content="planner input"), AIMessage(content="final answer")]},
            )

            content = writer.path.read_text(encoding="utf-8")

        self.assertIn("# Common Agent Session", content)
        self.assertIn("## User", content)
        self.assertIn("用户问题", content)
        self.assertIn("## Agent", content)
        self.assertIn("Human Message", content)
        self.assertIn("planner input", content)
        self.assertIn("Ai Message", content)
        self.assertIn("final answer", content)


if __name__ == "__main__":
    unittest.main()
