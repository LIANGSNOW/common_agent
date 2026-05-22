import unittest

from langchain_core.messages import AIMessage

from src.agents.sub_graph.web_search import (
    ResearchEvaluation,
    SubQuestion,
    append_or_reset,
    research_agent,
)


class _StructuredModel:
    def __init__(self, response, capture=None):
        self.response = response
        self.capture = capture

    def invoke(self, prompt):
        if self.capture is not None:
            self.capture.append(prompt)
        return self.response


class _EvaluationModel:
    def __init__(self, response, capture):
        self.response = response
        self.capture = capture

    def with_structured_output(self, schema):
        return _StructuredModel(self.response, self.capture)


class WebSearchAgentTests(unittest.TestCase):
    def test_append_or_reset_appends_parallel_results_and_clears_on_empty_list(self):
        first = [{"intent": "first"}]
        second = [{"intent": "second"}]

        self.assertEqual(append_or_reset([], first), first)
        self.assertEqual(append_or_reset(first, second), first + second)
        self.assertEqual(append_or_reset(first + second, []), [])

    def test_web_search_returns_full_and_current_round_results(self):
        agent = object.__new__(research_agent)
        evidence = [
            {
                "title": "AI report",
                "url": "https://example.com/ai",
                "content": "Model progress",
                "date": "2026-05-01",
            }
        ]
        agent._search = lambda queries: evidence
        agent._summarize = lambda intent, docs, user_query: "模型能力持续提升。"

        result = agent.web_search(
            {
                "user_query": "AI 最近有什么进展？",
                "subquestion": {
                    "intent": "梳理近期模型进展",
                    "queries": ["AI model progress 2026"],
                },
            }
        )

        expected = [
            {
                "intent": "梳理近期模型进展",
                "queries": ["AI model progress 2026"],
                "summary": "模型能力持续提升。",
                "evidence": evidence,
            }
        ]
        self.assertEqual(result["search_results"], expected)
        self.assertEqual(result["last_search_results"], expected)
        self.assertIn("梳理近期模型进展", result["messages"][0].content)

    def test_evaluate_uses_current_round_results_and_previous_evaluation(self):
        prompts = []
        evaluation = ResearchEvaluation(
            is_sufficient=True,
            confidence="high",
            covered_aspects=["最新模型能力"],
            missing_aspects=[],
            followup_queries=[],
        )
        agent = object.__new__(research_agent)
        agent.llm = _EvaluationModel(evaluation, prompts)

        result = agent.evaluate(
            {
                "user_query": "AI 最近有什么进展？",
                "research_plan": {"research_goal": "了解 AI 趋势"},
                "evaluation": {"missing_aspects": ["行业采用"]},
                "search_results": [
                    {"intent": "旧问题", "summary": "旧结果", "queries": [], "evidence": []}
                ],
                "last_search_results": [
                    {"intent": "新问题", "summary": "新结果", "queries": [], "evidence": []}
                ],
            }
        )

        self.assertEqual(result["evaluation"]["is_sufficient"], True)
        self.assertEqual(result["followup_queries"], [])
        self.assertIn("新结果", prompts[0])
        self.assertNotIn("旧结果", prompts[0])
        self.assertIn("行业采用", prompts[0])

    def test_prepare_followup_resets_current_round_and_reuses_followup_queries(self):
        agent = object.__new__(research_agent)

        result = agent.prepare_followup(
            {
                "current_index": 1,
                "followup_queries": [
                    {
                        "intent": "补充行业采用",
                        "queries": ["AI adoption enterprise 2026"],
                    }
                ],
            }
        )

        self.assertEqual(result["last_search_results"], [])
        self.assertEqual(result["current_index"], 2)
        self.assertEqual(
            result["subquestions"],
            [
                {
                    "intent": "补充行业采用",
                    "queries": ["AI adoption enterprise 2026"],
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
