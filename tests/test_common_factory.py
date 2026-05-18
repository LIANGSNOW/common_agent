import unittest

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import HumanMessage

from src.agents.common import create_common_agent


class CommonAgentFactoryTests(unittest.TestCase):
    def test_common_agent_runs_planner_then_codeact(self):
        model = FakeListChatModel(
            responses=[
                '{"summary":"Add two numbers","steps":["Use Python"],"capabilities":["python"]}',
                "```python\n<execute>\nprint(2 + 3)\n</execute>\n```",
                "The answer is 5.",
            ]
        )

        agent = create_common_agent(model=model)
        result = agent.invoke({"messages": [HumanMessage(content="What is 2 + 3?")]})

        self.assertEqual(result["plan"].summary, "Add two numbers")
        self.assertEqual(result["messages"][-1].content, "The answer is 5.")
        message_text = "\n".join(str(message.content) for message in result["messages"])
        self.assertIn("Sandbox code", message_text)
        self.assertIn("print(2 + 3)", message_text)
        self.assertIn("Sandbox output", message_text)
        self.assertIn("5", message_text)
        self.assertEqual(message_text.count("Plan summary:"), 1)
        self.assertNotIn("Planner context:", message_text)
        self.assertIn("codeact_result", result)


if __name__ == "__main__":
    unittest.main()
