import io
import unittest
from unittest.mock import patch

from langchain_core.messages import HumanMessage

from src.cli_common_agent import collect_multiline_input, run_from_stdin, run_once


class FakeMessage:
    def __init__(self):
        self.pretty_print_called = False

    def pretty_print(self):
        self.pretty_print_called = True


class FakeAgent:
    def __init__(self, message):
        self.message = message
        self.received_input = None

    def invoke(self, agent_input):
        self.received_input = agent_input
        return {"messages": [self.message]}


class CliCommonAgentTests(unittest.TestCase):
    def test_run_once_invokes_agent_with_human_message_and_prints_result(self):
        message = FakeMessage()
        fake_agent = FakeAgent(message)

        with patch("src.cli_common_agent.create_common_agent", return_value=fake_agent):
            result = run_once("hello")

        sent_message = fake_agent.received_input["messages"][0]
        self.assertIsInstance(sent_message, HumanMessage)
        self.assertEqual(sent_message.content, "hello")
        self.assertTrue(message.pretty_print_called)
        self.assertEqual(result, {"messages": [message]})

    def test_run_from_stdin_treats_all_text_as_one_request(self):
        message = FakeMessage()
        fake_agent = FakeAgent(message)
        stdin = io.StringIO("第一行\n\n第二行\n第三行\n")

        with patch("src.cli_common_agent.create_common_agent", return_value=fake_agent):
            result = run_from_stdin(stdin)

        sent_message = fake_agent.received_input["messages"][0]
        self.assertEqual(sent_message.content, "第一行\n\n第二行\n第三行\n")
        self.assertTrue(message.pretty_print_called)
        self.assertEqual(result, {"messages": [message]})

    def test_collect_multiline_input_until_end_marker(self):
        lines = iter(["第一行", "", "第二行", "/end"])

        result = collect_multiline_input(input_fn=lambda _: next(lines), output_fn=lambda _: None)

        self.assertEqual(result, "第一行\n\n第二行")


if __name__ == "__main__":
    unittest.main()
