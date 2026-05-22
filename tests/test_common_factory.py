import unittest
from unittest.mock import patch

from src.agents.common.factory import create_common_agent
from src.agents.common.state import CommonAgentState


class _FakeGraph:
    def __init__(self):
        self.config = None

    def with_config(self, config):
        self.config = config
        return self


class CommonAgentFactoryTests(unittest.TestCase):
    def test_common_agent_builds_configured_coordinator(self):
        fake_graph = _FakeGraph()
        model = object()

        with (
            patch("src.agents.common.factory.create_agent", return_value=fake_graph) as create_agent_mock,
            patch("src.agents.common.factory.build_coordinator_tools", return_value=["tool"]) as tools_mock,
            patch("src.agents.common.factory.render_system_prompt", return_value="coordinator prompt"),
        ):
            result = create_common_agent(model=model, recursion_limit=23)

        self.assertIs(result, fake_graph)
        self.assertEqual(fake_graph.config, {"recursion_limit": 23})
        tools_mock.assert_called_once_with(model=model)
        create_agent_mock.assert_called_once_with(
            model=model,
            tools=["tool"],
            system_prompt="coordinator prompt",
            state_schema=CommonAgentState,
        )


if __name__ == "__main__":
    unittest.main()
