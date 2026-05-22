from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Callable

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command, interrupt

from src.agents.code import CodeActState, create_codeact
from src.agents.common.sandbox import local_python_sandbox
from src.agents.common.state import CommonAgentState, Todo
from src.agents.sub_graph.web_search import research_agent


_codeact_by_model: dict[int, Any] = {}
_dr_singleton: Any | None = None


def _default_workspace() -> str:
    return f"./output/{datetime.now().strftime('%Y%m%d-%H%M%S')}"


def _default_codeact_factory(model: BaseChatModel):
    key = id(model)
    if key not in _codeact_by_model:
        _codeact_by_model[key] = create_codeact(model=model, eval_fn=local_python_sandbox)
    return _codeact_by_model[key]


def _default_dr_factory():
    global _dr_singleton
    if _dr_singleton is None:
        _dr_singleton = research_agent().create_agent()
    return _dr_singleton


def _format_plan(todos: list[Todo]) -> str:
    if not todos:
        return "Plan cleared."
    lines = ["Plan updated:"]
    for todo in todos:
        lines.append(f"- [{todo['status']}] {todo['id']}: {todo['content']}")
    return "\n".join(lines)


def _last_message_content(result: dict[str, Any], fallback: str) -> str:
    messages = result.get("messages", [])
    if messages:
        return str(getattr(messages[-1], "content", messages[-1]))
    return str(result.get("answer") or fallback)


def _extract_sources(result: dict[str, Any]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for item in result.get("search_results", []) or []:
        for source in item.get("evidence", []) or []:
            sources.append(
                {
                    "title": source.get("title", ""),
                    "url": source.get("url", ""),
                    "date": source.get("date", "Unknown"),
                }
            )
    return sources


def build_coordinator_tools(
    *,
    model: BaseChatModel,
    codeact_factory: Callable[[BaseChatModel], Any] = _default_codeact_factory,
    dr_factory: Callable[[], Any] = _default_dr_factory,
):
    @tool
    def update_plan(
        todos: list[Todo],
        state: Annotated[CommonAgentState, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """Create or replace the full todo list. Use proactively for tasks with 3+ distinct steps.

        Calling this tool will pause execution and ask the user to confirm the plan. If the user
        replies anything other than "accept" (or a Chinese affirmative), treat the response as
        revision feedback and call update_plan again with a revised plan.
        """
        formatted = _format_plan(todos)
        user_response = interrupt(
            {
                "type": "confirm_plan",
                "question": "请确认这个 plan。回复 accept 表示同意；其他回复将被视为修改意见。",
                "plan": formatted,
            }
        )
        normalized = str(user_response).strip().lower()
        approved = normalized in {"accept", "ok", "yes", "y", "同意", "可以", "好", "好的", "确认", "approve", "approved"}
        verdict = "用户已同意该 plan。" if approved else f"用户对该 plan 有反馈：{user_response}。请根据反馈调用 update_plan 修订计划。"
        return Command(
            update={
                "plan": todos,
                "messages": [
                    ToolMessage(
                        content=f"{formatted}\n\n{verdict}",
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )

    @tool
    def ask_human(
        question: str,
        tool_call_id: Annotated[str, InjectedToolCallId],
        options: list[str] | None = None,
    ) -> Command:
        """Ask the human user for input when you genuinely need their judgment.

        Use sparingly. Only call this when you cannot reasonably decide on your own — for example:
        multiple valid paths with non-obvious tradeoffs, ambiguous user requirements, or surprising
        intermediate results that need a human decision. Don't ask things you can determine yourself.

        Args:
            question: The question to present to the user (Chinese preferred).
            options: Optional list of suggested answers. The user is not restricted to these.
        """
        payload: dict[str, Any] = {"type": "ask_human", "question": question}
        if options:
            payload["options"] = options
        user_response = interrupt(payload)
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=f"用户回复：{user_response}",
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )

    @tool
    def deep_research(
        query: str,
        state: Annotated[CommonAgentState, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """Conduct deep web research on a focused topic with source-backed reporting.

        The query is your research goal, not the user's raw request. Phrase it as subject + time range + information type.
        """
        dr = dr_factory()
        result = dr.invoke({"messages": [HumanMessage(content=query)]})
        report = str(result.get("answer") or _last_message_content(result, "No research report produced."))
        finding = {
            "query": query,
            "report": report,
            "sources": _extract_sources(result),
        }
        return Command(
            update={
                "dr_findings": [finding],
                "messages": [ToolMessage(content=report, tool_call_id=tool_call_id)],
            }
        )

    @tool
    def run_codeact(
        task: str,
        state: Annotated[CommonAgentState, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """Run a self-contained Python/data/file-generation task through the CodeAct sub-agent.

        Include any research findings, workspace constraints, and relevant skill names in the task text.
        """
        workspace = state.get("workspace") or _default_workspace()
        Path(workspace).mkdir(parents=True, exist_ok=True)
        codeact = codeact_factory(model)
        codeact_state = CodeActState(
            messages=[
                HumanMessage(
                    content=(
                        f"{task}\n\n"
                        f"Workspace directory (create files here unless the user asked otherwise): {workspace}"
                    )
                )
            ],
            script=None,
            tool_command=None,
            context={},
            execution_summary=None,
        )
        result = codeact.invoke(codeact_state, config={"recursion_limit": 40})
        summary = _last_message_content(result, "No CodeAct result produced.")
        artifact = {"task": task, "summary": summary, "workspace": workspace}
        return Command(
            update={
                "codeact_artifacts": [artifact],
                "messages": [ToolMessage(content=summary, tool_call_id=tool_call_id)],
            }
        )

    return [update_plan, ask_human, deep_research, run_codeact]
