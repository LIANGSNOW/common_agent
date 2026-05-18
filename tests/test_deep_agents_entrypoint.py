import importlib
import unittest
from unittest.mock import patch


class DeepAgentsEntrypointTests(unittest.TestCase):
    def test_main_delegates_to_repl_for_interactive_terminal(self):
        deep_agents = importlib.import_module("deep_agents")

        with patch.object(deep_agents.sys.stdin, "isatty", return_value=True):
            with patch.object(deep_agents, "run_repl") as run_repl:
                deep_agents.main()

        run_repl.assert_called_once_with()

    def test_main_reads_all_stdin_as_one_request_for_piped_input(self):
        deep_agents = importlib.import_module("deep_agents")

        with patch.object(deep_agents.sys.stdin, "isatty", return_value=False):
            with patch.object(deep_agents, "run_from_stdin") as run_from_stdin:
                deep_agents.main()

        run_from_stdin.assert_called_once_with(deep_agents.sys.stdin)


if __name__ == "__main__":
    unittest.main()
