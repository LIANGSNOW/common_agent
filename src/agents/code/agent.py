import inspect
from typing import (
    Any,
    Awaitable,
    Callable,
    Literal,
    Type,
    TypeAlias,
)

from deepagents.graph import CompiledStateGraph
from langchain.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.language_models import BaseChatModel
from langchain_core.messages.utils import AnyMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.managed.is_last_step import RemainingSteps

from .prompts import (
    DEFAULT_PROMPT_TEMPLATE,
    FINAL_SUMMARY_ANSWER_TEMPLATE,
    SUMMARY_PROMPT_TEMPLATE,
)
from .skills_tools import SKILL_DICT
from .utils import extract_and_combine_codeblocks, extract_tool_command

EvalFunction: TypeAlias = Callable[[str, dict[str, Any]], tuple[str, dict[str, Any]]]
EvalCoroutine: TypeAlias = Callable[
    [str, dict[str, Any]], Awaitable[tuple[str, dict[str, Any]]]
]


class CodeActState(MessagesState):
    """CodeAct agent的全局state_schema。"""

    script: str | None
    tool_command: dict[str, dict[str, str]] | None
    context: dict[str, Any]
    remaining_steps: RemainingSteps
    execution_summary: str | None


# StateSchema = TypeVar(name="StateSchema", bound=CodeActState)
# StateSchemaType: TypeAlias = Type[StateSchema]


def create_codeact(
    model: BaseChatModel,
    eval_fn: EvalFunction | EvalCoroutine,
    *,
    prompt: str | None = None,
    # checkpoint: str | None = None,
    state_schema: Type[CodeActState] = CodeActState,
) -> CompiledStateGraph:
    final_prompt: str = DEFAULT_PROMPT_TEMPLATE if prompt is None else prompt

    def call_model(state: CodeActState) -> dict[str, Any]:
        """调用语言模型生成响应并处理剩余步数。"""
        # 检查剩余步数
        remaining: RemainingSteps = state.get("remaining_steps")

        # 当剩余步数小于等于2时，生成执行总结并结束
        if remaining is not None and remaining <= 2:
            conversation_history: list[AnyMessage] = state.get("messages", [])

            # 生成执行过程总结
            summary_prompt: str = SUMMARY_PROMPT_TEMPLATE.format(
                conversation_history=conversation_history
            )

            summary_messages: list[AnyMessage] = [SystemMessage(content=summary_prompt)]

            # 包含最近的消息作为上下文
            recent_messages: list[AnyMessage] = (
                state["messages"][-10:]
                if len(state["messages"]) > 5
                else state["messages"]
            )
            for msg in recent_messages:
                if isinstance(msg, dict):
                    summary_messages.append(msg)

            summary_response: AIMessage = model.invoke(input=summary_messages)

            # 构建最终总结消息
            final_message: str = FINAL_SUMMARY_ANSWER_TEMPLATE.format(
                summary_response=summary_response.content
            )

            return {
                "messages": [AIMessage(content=final_message)],
                "execution_summary": final_message,
                "script": None,
            }

        # 正常执行流程
        messages: list[AnyMessage] = [SystemMessage(content=final_prompt)] + state[
            "messages"
        ]
        response: AIMessage = model.invoke(input=messages)

        code: str = extract_and_combine_codeblocks(text=str(response.content))
        tool_command: dict[str, dict[str, Any]] | None = extract_tool_command(
            text=str(response.content)
        )

        return {
            "messages": [response],
            "script": code if code else None,
            "tool_command": tool_command if tool_command else None,
        }

    def should_continue(
        state: CodeActState,
    ) -> Literal["sandbox", "tool_command", "END"]:
        """根据状态决定下一步操作。"""
        # 检查是否有代码需要执行
        if state.get("script"):
            return "sandbox"
        # 检查是否有工具命令需要执行
        elif state.get("tool_command"):
            return "tool_command"
        else:
            # 没有代码块或已生成总结，结束循环
            return "END"

    def tool_command(state: CodeActState):
        tool_info: dict[str, dict[str, str]] | None = state.get("tool_command")
        if tool_info:
            for key, value in tool_info.items():
                if key in SKILL_DICT:
                    func = SKILL_DICT[key]
                    # Check if function requires arguments by inspecting its signature
                    sig = inspect.signature(func)
                    required_params = [
                        param.name 
                        for param in sig.parameters.values() 
                        if param.default == inspect.Parameter.empty and param.kind != inspect.Parameter.VAR_KEYWORD
                    ]
                    
                    # If function requires parameters but value is empty, return error
                    if required_params and (not value or len(value) == 0):
                        error_msg = f"Function '{key}' requires parameters: {', '.join(required_params)}, but none were provided."
                        return {"messages": [HumanMessage(content=error_msg)]}
                    
                    # Call function with parameters if provided, otherwise without
                    if value and len(value) > 0:
                        try:
                            result = func(**value)
                            return {"messages": [HumanMessage(content=result)]}
                        except TypeError as e:
                            error_msg = f"Error calling '{key}': {str(e)}. Provided parameters: {value}"
                            return {"messages": [HumanMessage(content=error_msg)]}
                    else:
                        # Function doesn't require parameters
                        result = func()
                        return {"messages": [HumanMessage(content=result)]}

    # If eval_fn is a async, we define async node function.
    if inspect.iscoroutinefunction(eval_fn):

        async def sandbox_async(state: CodeActState) -> dict[str, Any]:
            existing_context: dict[str, Any] = state.get("context", {})
            context: dict[str, Any] = {**existing_context}
            script: str | None = state["script"]
            if script is None:
                return {
                    "messages": [{"role": "error", "content": "代码块为空，无法执行"}],
                    "context": existing_context,
                }
            output, new_vars = await eval_fn(script, context)
            new_context = {**existing_context, **new_vars}
            trace = (
                "Sandbox code:\n"
                f"```python\n{script}\n```\n\n"
                "Sandbox output:\n"
                f"```text\n{output}\n```"
            )
            return {
                "messages": [HumanMessage(content=trace)],
                "context": new_context,
            }

        sandbox = sandbox_async
    else:

        def sync_sandbox(state: CodeActState) -> dict[str, Any]:
            existing_context: dict[str, Any] = state.get("context", {})
            context: dict[str, Any] = {**existing_context}
            # Execute the script in the sandbox
            script: str | None = state["script"]
            if script is None:
                return {
                    "messages": [{"role": "error", "content": "代码块为空，无法执行"}],
                    "context": existing_context,
                }
            output, new_vars = eval_fn(script, context)  # type: ignore
            new_context: dict[str, Any] = {**existing_context, **new_vars}
            trace = (
                "Sandbox code:\n"
                f"```python\n{script}\n```\n\n"
                "Sandbox output:\n"
                f"```text\n{output}\n```"
            )
            return {
                "messages": [HumanMessage(content=trace)],
                "context": new_context,
            }

        sandbox = sync_sandbox

    # 构建状态图
    agent = StateGraph(state_schema)

    # 添加节点
    agent.add_node("call_model", call_model)
    agent.add_node("sandbox", sandbox)
    agent.add_node("tool_command", tool_command)

    # 添加边
    agent.add_edge(start_key=START, end_key="call_model")

    # 添加条件边：根据should_continue的返回值决定下一步
    agent.add_conditional_edges(
        source="call_model",
        path=should_continue,
        path_map={"sandbox": "sandbox", "tool_command": "tool_command", "END": END},
    )

    # sandbox执行后返回call_model
    agent.add_edge("sandbox", "call_model")
    agent.add_edge("tool_command", "call_model")

    return agent.compile()
