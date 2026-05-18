import json
import unittest

from langchain_core.language_models.fake_chat_models import FakeListChatModel

from src.agents.common.planner import PlannerOutput, parse_planner_output, run_planner


class PlannerTests(unittest.TestCase):
    def test_parse_valid_planner_json(self):
        raw = """
        {
          "summary": "Calculate a result",
          "steps": ["Inspect skills", "Run Python"],
          "capabilities": ["skills", "python"]
        }
        """

        result = parse_planner_output(raw)

        self.assertEqual(result.summary, "Calculate a result")
        self.assertEqual(result.steps, ["Inspect skills", "Run Python"])
        self.assertEqual(result.capabilities, ["skills", "python"])
        self.assertIsNone(result.target_skill)

    def test_parse_target_skill_when_present(self):
        raw = """
        {
          "summary": "Make a PPT",
          "steps": ["Read SKILL.md", "Copy template"],
          "capabilities": ["skills", "python"],
          "target_skill": "ppt"
        }
        """

        result = parse_planner_output(raw)

        self.assertEqual(result.target_skill, "ppt")
        self.assertIn("Target skill: ppt", result.to_context())

    def test_parse_target_skill_null_variants(self):
        for value in ["null", "none", "", None]:
            raw = (
                '{"summary":"x","steps":["a"],"capabilities":["python"],'
                f'"target_skill":{json.dumps(value)}}}'
            )
            result = parse_planner_output(raw)
            self.assertIsNone(result.target_skill, f"value={value!r}")

    def test_parse_markdown_wrapped_json(self):
        raw = """```json
        {"summary": "Research topic", "steps": ["Search web"], "capabilities": ["web_search"]}
        ```"""

        result = parse_planner_output(raw)

        self.assertEqual(result.summary, "Research topic")
        self.assertEqual(result.steps, ["Search web"])
        self.assertEqual(result.capabilities, ["web_search"])

    def test_fallback_for_invalid_json(self):
        result = parse_planner_output("not json")

        self.assertIsInstance(result, PlannerOutput)
        self.assertEqual(result.summary, "Proceed with a direct CodeAct attempt.")
        self.assertEqual(result.steps, ["Understand the request", "Use available capabilities", "Answer the user"])
        self.assertEqual(result.capabilities, ["skills", "python"])

    def test_run_planner_invokes_model_and_parses_result(self):
        model = FakeListChatModel(
            responses=[
                '{"summary":"Do arithmetic","steps":["Use Python"],"capabilities":["python"]}'
            ]
        )

        result = run_planner(model, "What is 2 + 3?")

        self.assertEqual(result.summary, "Do arithmetic")
        self.assertEqual(result.steps, ["Use Python"])
        self.assertEqual(result.capabilities, ["python"])


if __name__ == "__main__":
    unittest.main()
