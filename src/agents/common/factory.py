from datetime import datetime
from pathlib import Path
from typing import Any

from langchain.chat_models import BaseChatModel, init_chat_model
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.messages.utils import AnyMessage
from langgraph.graph import END, START, MessagesState, StateGraph

from src.agents.code import CodeActState, create_codeact
from src.agents.common.planner import PlannerOutput, run_planner
from src.agents.common.sandbox import local_python_sandbox


class CommonAgentState(MessagesState):
    plan: PlannerOutput | None
    codeact_result: dict[str, Any] | None
    workspace: str | None


def create_default_model() -> BaseChatModel:
    from src.config import llm_settings

    return init_chat_model(
        model=llm_settings.model_name,
        model_provider="openai",
        api_key=llm_settings.api_key,
        base_url=llm_settings.base_url,
        temperature=llm_settings.temperature,
    )


def _default_workspace() -> str:
    return f"./output/{datetime.now().strftime('%Y%m%d-%H%M%S')}"


def create_common_agent(
    model: BaseChatModel | None = None,
    *,
    recursion_limit: int = 60,
    workspace_dir: str | Path | None = None,
):
    selected_model = model or create_default_model()
    codeact = create_codeact(model=selected_model, eval_fn=local_python_sandbox)
    fixed_workspace = str(workspace_dir) if workspace_dir is not None else None

    def visible_codeact_messages(messages: list[AnyMessage]) -> list[AnyMessage]:
        if not messages:
            return []

        first_message = messages[0]
        first_content = str(getattr(first_message, "content", ""))
        if isinstance(first_message, HumanMessage) and "Planner context:" in first_content:
            return messages[1:]
        return messages

    def planner_node(state: CommonAgentState) -> dict[str, Any]:
        messages = state.get("messages", [])
        user_content = ""
        for message in reversed(messages):
            if isinstance(message, HumanMessage):
                user_content = str(message.content)
                break

        plan = run_planner(selected_model, user_content)
        workspace = state.get("workspace") or fixed_workspace or _default_workspace()
        return {
            "plan": plan,
            "workspace": workspace,
            "messages": [AIMessage(content=plan.to_context())],
        }

    def codeact_node(state: CommonAgentState) -> dict[str, Any]:
        messages = state.get("messages", [])
        plan = state.get("plan")
        plan_context = plan.to_context() if plan else "No planner context available."
        workspace = state.get("workspace") or fixed_workspace or _default_workspace()
        target_skill = plan.target_skill if plan else None
        original_user_messages = [message for message in messages if isinstance(message, HumanMessage)]
        user_message = original_user_messages[-1] if original_user_messages else HumanMessage(content="")

        skill_hint = ""
        if target_skill:
            skill_hint = (
                f"Skill onboarding hint: planner selected target_skill='{target_skill}'.\n"
                f"Before writing any execution code, do this in one turn:\n"
                f"  1) <list_skill_files>{{skill_type=\"{target_skill}\"}}</list_skill_files>\n"
                f"  2) <read_skill_file>{{skill_type=\"{target_skill}\", relative_path=\"skills.md\"}}</read_skill_file>\n"
                f"  3) If a SKILL.md or referenced workflow doc exists, read it before generating any script.\n"
                f"Only after that, plan the concrete file/code operations.\n\n"
            )

        codeact_state = CodeActState(
            messages=[
                HumanMessage(
                    content=(
                        f"{user_message.content}\n\n"
                        f"Planner context:\n{plan_context}\n\n"
                        f"Workspace directory (create on demand via pathlib.Path(...).mkdir(parents=True, exist_ok=True)): {workspace}\n\n"
                        f"{skill_hint}"
                        "Use the plan as guidance. Adjust if execution results show a better path."
                    )
                )
            ],
            script=None,
            tool_command=None,
            context={},
            execution_summary=None,
        )
        # recursion_limit must be passed via config; RemainingSteps managed value
        # in CodeActState is auto-computed by langgraph from this value.
        result = codeact.invoke(
            codeact_state,
            config={"recursion_limit": recursion_limit},
        )
        result_messages = result.get("messages", [])
        visible_messages = visible_codeact_messages(result_messages)
        final_message = result_messages[-1] if result_messages else AIMessage(content="No result produced.")
        return {
            "codeact_result": result,
            "messages": visible_messages or [final_message],
        }

    graph = StateGraph(CommonAgentState)
    graph.add_node("planner", planner_node)
    graph.add_node("codeact", codeact_node)
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "codeact")
    graph.add_edge("codeact", END)
    return graph.compile()
