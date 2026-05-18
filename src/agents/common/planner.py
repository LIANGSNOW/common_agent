import json
from dataclasses import dataclass

from langchain.messages import HumanMessage, SystemMessage
from langchain_core.language_models import BaseChatModel

from src.agents.code.skills_tools import list_skills


PLANNER_SYSTEM_PROMPT_TEMPLATE = """You are a lightweight planning node for a domain-neutral common agent.

Given a user request, produce a compact JSON plan before CodeAct execution.

Return only JSON with this shape:
{{
  "summary": "one sentence summary",
  "steps": ["short step 1", "short step 2"],
  "capabilities": ["skills", "python", "web_search"],
  "target_skill": "<skill name or null>"
}}

Available skills (choose target_skill from this catalog or null if none fits):
{skill_catalog}

Rules:
- Keep 2-5 steps.
- Use "skills" capability when reusable project skills may help.
- Use "python" when calculation, data manipulation, or local code execution may help.
- Use "web_search" when current or external information is needed.
- Set target_skill to the skill key (e.g. "math", "ppt") when one clearly fits; otherwise null.
- For procedural skills (skills with workflow docs like SKILL.md), the first step should be to read the skill's intro/index.
- Do not include domain-specific assumptions beyond the catalog.
"""


def build_planner_system_prompt() -> str:
    try:
        catalog_repr = list_skills()
        catalog_dict = eval(catalog_repr) if catalog_repr.startswith("{") else {}
    except Exception:
        catalog_dict = {}

    if not catalog_dict:
        catalog_text = "(no skills registered)"
    else:
        lines = []
        for name, intro in catalog_dict.items():
            intro_one_line = " ".join(str(intro).split())
            if len(intro_one_line) > 240:
                intro_one_line = intro_one_line[:240] + "..."
            lines.append(f"- {name}: {intro_one_line}")
        catalog_text = "\n".join(lines)

    return PLANNER_SYSTEM_PROMPT_TEMPLATE.format(skill_catalog=catalog_text)


@dataclass
class PlannerOutput:
    summary: str
    steps: list[str]
    capabilities: list[str]
    target_skill: str | None = None

    def to_context(self) -> str:
        steps = "\n".join(f"{index}. {step}" for index, step in enumerate(self.steps, start=1))
        capabilities = ", ".join(self.capabilities)
        target = self.target_skill or "none"
        return (
            f"Plan summary: {self.summary}\n"
            f"Target skill: {target}\n"
            f"Likely capabilities: {capabilities}\n"
            f"Steps:\n{steps}"
        )


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
        raw_target = payload.get("target_skill")
        target_skill: str | None
        if raw_target is None or raw_target == "" or (isinstance(raw_target, str) and raw_target.lower() in {"null", "none"}):
            target_skill = None
        else:
            target_skill = str(raw_target)
        return PlannerOutput(
            summary=summary,
            steps=steps,
            capabilities=capabilities,
            target_skill=target_skill,
        )
    except Exception:
        return PlannerOutput(
            summary="Proceed with a direct CodeAct attempt.",
            steps=["Understand the request", "Use available capabilities", "Answer the user"],
            capabilities=["skills", "python"],
            target_skill=None,
        )


def run_planner(model: BaseChatModel, user_input: str) -> PlannerOutput:
    response = model.invoke(
        [
            SystemMessage(content=build_planner_system_prompt()),
            HumanMessage(content=user_input),
        ]
    )
    return parse_planner_output(str(response.content))
