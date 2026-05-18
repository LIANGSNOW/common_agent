# CLI Common Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a domain-neutral CLI demo runner that creates a common agent with a lightweight planner, CodeAct execution, skill discovery, and trusted local Python sandbox.

**Architecture:** Add a small common-agent graph that runs `planner -> codeact_executor`. Keep skills and sandbox as runtime capabilities, not middleware. Reuse `src/agents/code/create_codeact` and move the current local `exec` behavior into a reusable sandbox module.

**Tech Stack:** Python 3.12, LangGraph, LangChain, existing CodeAct runtime, standard-library `unittest`.

---

## File Structure

- Create `src/agents/common/__init__.py`: exports the common-agent factory and state.
- Create `src/agents/common/factory.py`: builds the planner-plus-CodeAct graph.
- Create `src/agents/common/planner.py`: lightweight planner prompt and parser.
- Create `src/agents/common/sandbox.py`: trusted local Python execution function.
- Create `src/cli_common_agent.py`: CLI demo runner.
- Create `tests/test_common_sandbox.py`: unit tests for sandbox execution.
- Create `tests/test_common_planner.py`: unit tests for planner parsing/fallback behavior.
- Modify `README.md`: add the CLI demo command and trusted-local warning.
- Optional later cleanup, not part of this plan: convert `deep_agents.py` from stock demo to compatibility shim.

## Task 1: Extract Local Python Sandbox

**Files:**
- Create: `src/agents/common/__init__.py`
- Create: `src/agents/common/sandbox.py`
- Test: `tests/test_common_sandbox.py`

- [ ] **Step 1: Write the failing sandbox tests**

Create `tests/test_common_sandbox.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
python -m unittest tests.test_common_sandbox -v
```

Expected: FAIL or ERROR because `src.agents.common.sandbox` does not exist.

- [ ] **Step 3: Add the common package export**

Create `src/agents/common/__init__.py`:

```python
from .sandbox import local_python_sandbox

__all__ = ["local_python_sandbox"]
```

- [ ] **Step 4: Implement the sandbox**

Create `src/agents/common/sandbox.py`:

```python
import builtins
import contextlib
import io
import sys
from pathlib import Path
from typing import Any


def local_python_sandbox(code: str, local_context: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Execute trusted local Python code and return stdout plus newly created vars.

    This is intentionally not a security sandbox. It is for local CLI demo use only.
    """
    project_root = Path(__file__).resolve().parents[3]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    original_keys = set(local_context.keys())

    try:
        with contextlib.redirect_stdout(io.StringIO()) as output_buffer:
            exec(code, builtins.__dict__, local_context)
        output = output_buffer.getvalue() or "<code ran, no output printed to stdout>"
    except Exception as exc:
        output = f"Error during execution: {repr(exc)}"

    new_keys = set(local_context.keys()) - original_keys
    new_vars = {key: local_context[key] for key in new_keys}
    return output, new_vars
```

- [ ] **Step 5: Run the tests to verify they pass**

Run:

```bash
python -m unittest tests.test_common_sandbox -v
```

Expected: PASS for all three tests.

- [ ] **Step 6: Commit**

```bash
git add src/agents/common/__init__.py src/agents/common/sandbox.py tests/test_common_sandbox.py
git commit -m "feat: add local python sandbox"
```

## Task 2: Add Lightweight Planner

**Files:**
- Create: `src/agents/common/planner.py`
- Modify: `src/agents/common/__init__.py`
- Test: `tests/test_common_planner.py`

- [ ] **Step 1: Write the failing planner tests**

Create `tests/test_common_planner.py`:

```python
import unittest

from src.agents.common.planner import PlannerOutput, parse_planner_output


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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
python -m unittest tests.test_common_planner -v
```

Expected: FAIL or ERROR because `src.agents.common.planner` does not exist.

- [ ] **Step 3: Implement planner parsing and prompt constants**

Create `src/agents/common/planner.py`:

```python
import json
from dataclasses import dataclass


PLANNER_SYSTEM_PROMPT = """You are a lightweight planning node for a domain-neutral common agent.

Given a user request, produce a compact JSON plan before CodeAct execution.

Return only JSON with this shape:
{
  "summary": "one sentence summary",
  "steps": ["short step 1", "short step 2"],
  "capabilities": ["skills", "python", "web_search"]
}

Rules:
- Keep 2-5 steps.
- Use "skills" when reusable project skills may help.
- Use "python" when calculation, data manipulation, or local code execution may help.
- Use "web_search" when current or external information is needed.
- Do not include domain-specific assumptions.
"""


@dataclass
class PlannerOutput:
    summary: str
    steps: list[str]
    capabilities: list[str]

    def to_context(self) -> str:
        steps = "\n".join(f"{index}. {step}" for index, step in enumerate(self.steps, start=1))
        capabilities = ", ".join(self.capabilities)
        return f"Plan summary: {self.summary}\nLikely capabilities: {capabilities}\nSteps:\n{steps}"


def parse_planner_output(raw: str) -> PlannerOutput:
    content = raw.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    try:
        payload = json.loads(content)
        summary = str(payload["summary"])
        steps = [str(step) for step in payload["steps"]]
        capabilities = [str(capability) for capability in payload["capabilities"]]
        if not summary or not steps or not capabilities:
            raise ValueError("Planner output must include summary, steps, and capabilities")
        return PlannerOutput(summary=summary, steps=steps, capabilities=capabilities)
    except Exception:
        return PlannerOutput(
            summary="Proceed with a direct CodeAct attempt.",
            steps=["Understand the request", "Use available capabilities", "Answer the user"],
            capabilities=["skills", "python"],
        )
```

- [ ] **Step 4: Update common package exports**

Modify `src/agents/common/__init__.py`:

```python
from .planner import PLANNER_SYSTEM_PROMPT, PlannerOutput, parse_planner_output
from .sandbox import local_python_sandbox

__all__ = [
    "PLANNER_SYSTEM_PROMPT",
    "PlannerOutput",
    "local_python_sandbox",
    "parse_planner_output",
]
```

- [ ] **Step 5: Run the planner tests**

Run:

```bash
python -m unittest tests.test_common_planner -v
```

Expected: PASS for all three tests.

- [ ] **Step 6: Run all current common tests**

Run:

```bash
python -m unittest tests.test_common_sandbox tests.test_common_planner -v
```

Expected: PASS for all tests.

- [ ] **Step 7: Commit**

```bash
git add src/agents/common/__init__.py src/agents/common/planner.py tests/test_common_planner.py
git commit -m "feat: add lightweight planner"
```

## Task 3: Add Common Agent Factory

**Files:**
- Create: `src/agents/common/factory.py`
- Modify: `src/agents/common/__init__.py`
- Test: manual import and graph build command

- [ ] **Step 1: Add the factory module**

Create `src/agents/common/factory.py`:

```python
from typing import Any

from langchain.chat_models import BaseChatModel, init_chat_model
from langchain.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, MessagesState, StateGraph

from src.agents.code import CodeActState, create_codeact
from src.agents.common.planner import PLANNER_SYSTEM_PROMPT, PlannerOutput, parse_planner_output
from src.agents.common.sandbox import local_python_sandbox
from src.config import llm_settings


class CommonAgentState(MessagesState):
    plan: PlannerOutput | None
    codeact_result: dict[str, Any] | None


def create_default_model() -> BaseChatModel:
    return init_chat_model(
        model=llm_settings.model_name,
        model_provider="openai",
        api_key=llm_settings.api_key,
        base_url=llm_settings.base_url,
        temperature=llm_settings.temperature,
    )


def create_common_agent(
    model: BaseChatModel | None = None,
    *,
    recursion_limit: int = 20,
):
    selected_model = model or create_default_model()
    codeact = create_codeact(model=selected_model, eval_fn=local_python_sandbox)

    def planner_node(state: CommonAgentState) -> dict[str, Any]:
        messages = state.get("messages", [])
        user_content = ""
        for message in reversed(messages):
            if isinstance(message, HumanMessage):
                user_content = str(message.content)
                break

        response = selected_model.invoke(
            [
                SystemMessage(content=PLANNER_SYSTEM_PROMPT),
                HumanMessage(content=user_content),
            ]
        )
        plan = parse_planner_output(str(response.content))
        return {
            "plan": plan,
            "messages": [AIMessage(content=plan.to_context())],
        }

    def codeact_node(state: CommonAgentState) -> dict[str, Any]:
        messages = state.get("messages", [])
        plan = state.get("plan")
        plan_context = plan.to_context() if plan else "No planner context available."
        original_user_messages = [message for message in messages if isinstance(message, HumanMessage)]
        user_message = original_user_messages[-1] if original_user_messages else HumanMessage(content="")

        codeact_state = CodeActState(
            messages=[
                HumanMessage(
                    content=(
                        f"{user_message.content}\n\n"
                        f"Planner context:\n{plan_context}\n\n"
                        "Use the plan as guidance. Adjust if execution results show a better path."
                    )
                )
            ],
            script=None,
            tool_command=None,
            context={},
            remaining_steps=recursion_limit,
            execution_summary=None,
        )
        result = codeact.invoke(codeact_state)
        result_messages = result.get("messages", [])
        final_message = result_messages[-1] if result_messages else AIMessage(content="No result produced.")
        return {
            "codeact_result": result,
            "messages": [final_message],
        }

    graph = StateGraph(CommonAgentState)
    graph.add_node("planner", planner_node)
    graph.add_node("codeact", codeact_node)
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "codeact")
    graph.add_edge("codeact", END)
    return graph.compile()
```

- [ ] **Step 2: Export the factory**

Modify `src/agents/common/__init__.py`:

```python
from .factory import CommonAgentState, create_common_agent, create_default_model
from .planner import PLANNER_SYSTEM_PROMPT, PlannerOutput, parse_planner_output
from .sandbox import local_python_sandbox

__all__ = [
    "CommonAgentState",
    "PLANNER_SYSTEM_PROMPT",
    "PlannerOutput",
    "create_common_agent",
    "create_default_model",
    "local_python_sandbox",
    "parse_planner_output",
]
```

- [ ] **Step 3: Verify the module imports**

Run:

```bash
python -c "from src.agents.common import create_common_agent, local_python_sandbox, parse_planner_output; print('common imports ok')"
```

Expected:

```text
common imports ok
```

- [ ] **Step 4: Verify graph build with a fake model**

Run:

```bash
python - <<'PY'
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from src.agents.common import create_common_agent

model = FakeListChatModel(responses=[
    '{"summary":"Add two numbers","steps":["Use Python"],"capabilities":["python"]}',
    '```python\n<execute>\nprint(2 + 3)\n</execute>\n```',
    'The answer is 5.'
])
agent = create_common_agent(model=model)
result = agent.invoke({"messages": "What is 2 + 3?"})
print(type(result["messages"][-1]).__name__)
print(result["messages"][-1].content)
PY
```

Expected: command exits successfully and prints a final message from the graph.

- [ ] **Step 5: Commit**

```bash
git add src/agents/common/__init__.py src/agents/common/factory.py
git commit -m "feat: add common agent factory"
```

## Task 4: Add CLI Demo Runner

**Files:**
- Create: `src/cli_common_agent.py`
- Modify: `README.md`

- [ ] **Step 1: Add the CLI runner**

Create `src/cli_common_agent.py`:

```python
from langchain_core.messages import HumanMessage

from src.agents.common import create_common_agent


def run_once(user_input: str) -> None:
    agent = create_common_agent()
    result = agent.invoke({"messages": [HumanMessage(content=user_input)]})
    for message in result.get("messages", []):
        message.pretty_print()


def run_repl() -> None:
    agent = create_common_agent()
    print("Common Agent CLI. Type 'exit' or 'quit' to stop.")
    while True:
        user_input = input("\n> ").strip()
        if user_input.lower() in {"exit", "quit"}:
            break
        if not user_input:
            continue

        result = agent.invoke({"messages": [HumanMessage(content=user_input)]})
        for message in result.get("messages", []):
            message.pretty_print()


if __name__ == "__main__":
    run_repl()
```

- [ ] **Step 2: Update README with CLI usage**

Replace the old stock-oriented README with this content:

````markdown
# Common Agent

This project is being refactored into a domain-neutral common agent. The first milestone is a CLI demo runner built around a lightweight planner, CodeAct execution, skill discovery, and trusted local Python execution.

## CLI Demo

Create a `.env` file with the LLM settings expected by `src/config/llm_config.py`:

```env
llm_model_name=your-model
llm_api_key=your-api-key
llm_base_url=your-base-url
llm_temperature=0.7
```

Run:

```bash
python -m src.cli_common_agent
```

The first sandbox implementation executes local Python with normal local privileges. Use it only in trusted local development environments.
````

- [ ] **Step 3: Run import verification**

Run:

```bash
python -m py_compile src/cli_common_agent.py src/agents/common/factory.py src/agents/common/planner.py src/agents/common/sandbox.py
```

Expected: no output and exit code 0.

- [ ] **Step 4: Commit**

```bash
git add src/cli_common_agent.py README.md
git commit -m "feat: add common agent cli"
```

## Task 5: Final Verification

**Files:**
- No new files.

- [ ] **Step 1: Run unit tests**

Run:

```bash
python -m unittest tests.test_common_sandbox tests.test_common_planner -v
```

Expected: PASS for all tests.

- [ ] **Step 2: Run compile checks**

Run:

```bash
python -m py_compile src/agents/common/__init__.py src/agents/common/factory.py src/agents/common/planner.py src/agents/common/sandbox.py src/cli_common_agent.py src/agents/code/agent.py src/agents/code/skills_tools.py
```

Expected: no output and exit code 0.

- [ ] **Step 3: Run CLI smoke test manually**

Run:

```bash
python -m src.cli_common_agent
```

At the prompt, enter:

```text
用 Python 计算 2 + 3，并告诉我结果
```

Expected: the agent prints planner context and a final answer containing `5`. If LLM credentials are not configured, record that manual CLI smoke testing is blocked by missing credentials.

- [ ] **Step 4: Check git status**

Run:

```bash
git status --short
```

Expected: only pre-existing unrelated changes remain. New common-agent implementation files should be committed.
