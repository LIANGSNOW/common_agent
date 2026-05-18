import unittest

from src.agents.common.sandbox import local_python_sandbox


class LocalPythonSandboxTests(unittest.TestCase):
    def test_executes_python_and_returns_stdout(self):
        output, new_vars = local_python_sandbox("x = 2 + 3\nprint(x)", {})

        self.assertEqual(output.strip(), "5")
        self.assertEqual(new_vars["x"], 5)

    def test_preserves_existing_context_and_returns_only_new_vars(self):
        context = {"x": 10}

        output, new_vars = local_python_sandbox("y = x * 2\nprint(y)", context)

        self.assertEqual(output.strip(), "20")
        self.assertEqual(new_vars, {"y": 20})
        self.assertEqual(context["x"], 10)

    def test_returns_exception_text_without_raising(self):
        output, new_vars = local_python_sandbox("raise ValueError('bad input')", {})

        self.assertIn("Error during execution: ValueError('bad input')", output)
        self.assertEqual(new_vars, {})


if __name__ == "__main__":
    unittest.main()
