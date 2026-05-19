import unittest

from src.agents.code.utils import extract_and_combine_codeblocks


class ExtractCodeblocksTests(unittest.TestCase):
    def test_extracts_clean_execute_block(self):
        text = "<execute>\nimport math\nprint(math.ceil(1.2))\n</execute>"
        self.assertEqual(
            extract_and_combine_codeblocks(text),
            "import math\nprint(math.ceil(1.2))",
        )

    def test_strips_inner_markdown_fence_with_language(self):
        # Regression: LLM wraps code with ```python ... ``` inside <execute>.
        # Old extractor left trailing ``` and exec() failed with SyntaxError.
        text = "<execute>\n```python\nimport math\nprint(math.ceil(1.2))\n```\n</execute>"
        result = extract_and_combine_codeblocks(text)
        self.assertNotIn("```", result)
        self.assertEqual(result, "import math\nprint(math.ceil(1.2))")

    def test_strips_inner_bare_markdown_fence(self):
        text = "<execute>\n```\nx = 1\n```\n</execute>"
        self.assertEqual(extract_and_combine_codeblocks(text), "x = 1")

    def test_returns_empty_when_no_execute_block(self):
        self.assertEqual(extract_and_combine_codeblocks("no code here"), "")

    def test_combines_multiple_execute_blocks(self):
        text = "<execute>\na=1\n</execute>\nfoo\n<execute>\nb=2\n</execute>"
        self.assertEqual(extract_and_combine_codeblocks(text), "a=1\n\nb=2")


if __name__ == "__main__":
    unittest.main()
