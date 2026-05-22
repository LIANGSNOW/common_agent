import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from src.agents.common.prompts import render_system_prompt
from src.agents.common.state import CommonAgentState
from src.agents.common.tools import build_coordinator_tools


class _FakeSubgraph:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def invoke(self, state, config=None):
        self.calls.append((state, config))
        return self.result


class _FakeGraph:
    def __init__(self):
        self.config = None

    def with_config(self, config):
        self.config = config
        return self


class CommonCoordinatorTests(unittest.TestCase):
    def test_render_system_prompt_includes_skill_catalog(self):
        with patch(
            "src.agents.common.prompts.list_skills",
            return_value="{'math': 'Math helper skill'}",
        ):
            prompt = render_system_prompt()

        self.assertIn("通用智能体协调器", prompt)
        self.assertIn("不要假装自己搜索网页", prompt)
        self.assertIn("不要假装自己执行 Python", prompt)
        self.assertIn("同一时间只能有一个 todo 处于 in_progress", prompt)
        self.assertIn("math", prompt)
        self.assertIn("Math helper skill", prompt)
        self.assertIn("deep_research", prompt)
        self.assertIn("run_codeact", prompt)

    def test_update_plan_replaces_plan_with_tool_message(self):
        tools = build_coordinator_tools(
            model=object(),
            codeact_factory=lambda model: _FakeSubgraph({}),
            dr_factory=lambda: _FakeSubgraph({}),
        )
        update_plan = {tool.name: tool for tool in tools}["update_plan"]
        todos = [
            {"id": "t1", "content": "Research current benchmarks", "status": "in_progress"},
            {"id": "t2", "content": "Generate comparison chart", "status": "pending"},
        ]

        result = update_plan.func(todos=todos, state={}, tool_call_id="call-plan")

        self.assertIsInstance(result, Command)
        self.assertEqual(result.update["plan"], todos)
        self.assertIsInstance(result.update["messages"][0], ToolMessage)
        self.assertEqual(result.update["messages"][0].tool_call_id, "call-plan")
        self.assertIn("Research current benchmarks", result.update["messages"][0].content)

    def test_deep_research_appends_finding(self):
        dr = _FakeSubgraph(
            {
                "answer": "## Report\n\n- [Source](https://example.com)",
                "search_results": [
                    {
                        "evidence": [
                            {
                                "title": "Source",
                                "url": "https://example.com",
                                "date": "2026-05-22",
                            }
                        ]
                    }
                ],
            }
        )
        tools = build_coordinator_tools(
            model=object(),
            codeact_factory=lambda model: _FakeSubgraph({}),
            dr_factory=lambda: dr,
        )
        deep_research = {tool.name: tool for tool in tools}["deep_research"]

        result = deep_research.func(
            query="2026 AI inference chip benchmark evidence",
            state={},
            tool_call_id="call-dr",
        )

        self.assertEqual(
            dr.calls[0][0]["messages"][0].content,
            "2026 AI inference chip benchmark evidence",
        )
        finding = result.update["dr_findings"][0]
        self.assertEqual(finding["query"], "2026 AI inference chip benchmark evidence")
        self.assertIn("Report", finding["report"])
        self.assertEqual(finding["sources"][0]["url"], "https://example.com")
        self.assertEqual(result.update["messages"][0].tool_call_id, "call-dr")

    def test_run_codeact_uses_workspace_and_appends_artifact(self):
        codeact = _FakeSubgraph({"messages": [AIMessage(content="Created chart.")]})
        tools = build_coordinator_tools(
            model=object(),
            codeact_factory=lambda model: codeact,
            dr_factory=lambda: _FakeSubgraph({}),
        )
        run_codeact = {tool.name: tool for tool in tools}["run_codeact"]

        result = run_codeact.func(
            task="Generate a benchmark chart.",
            state={"workspace": "./output/test-session"},
            tool_call_id="call-code",
        )

        self.assertIn("Generate a benchmark chart.", codeact.calls[0][0]["messages"][0].content)
        self.assertIn("./output/test-session", codeact.calls[0][0]["messages"][0].content)
        self.assertEqual(codeact.calls[0][1], {"recursion_limit": 40})
        artifact = result.update["codeact_artifacts"][0]
        self.assertEqual(artifact["summary"], "Created chart.")
        self.assertEqual(artifact["workspace"], "./output/test-session")
        self.assertEqual(result.update["messages"][0].tool_call_id, "call-code")

    def test_factory_builds_create_agent_coordinator(self):
        from src.agents.common.factory import create_common_agent

        fake_graph = _FakeGraph()

        with (
            patch("src.agents.common.factory.create_agent", return_value=fake_graph) as create_agent_mock,
            patch("src.agents.common.factory.build_coordinator_tools", return_value=[]) as tools_mock,
            patch("src.agents.common.factory.render_system_prompt", return_value="prompt") as prompt_mock,
        ):
            result = create_common_agent(model=object(), recursion_limit=17)

        self.assertIs(result, fake_graph)
        self.assertEqual(fake_graph.config, {"recursion_limit": 17})
        tools_mock.assert_called_once()
        prompt_mock.assert_called_once()
        create_agent_mock.assert_called_once()
        kwargs = create_agent_mock.call_args.kwargs
        self.assertEqual(kwargs["tools"], [])
        self.assertEqual(kwargs["system_prompt"], "prompt")
        self.assertIs(kwargs["state_schema"], CommonAgentState)


if __name__ == "__main__":
    unittest.main()
