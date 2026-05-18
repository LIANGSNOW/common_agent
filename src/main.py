import builtins
import contextlib
import io
import sys
from pathlib import Path
from typing import Any

from langchain.chat_models import BaseChatModel, init_chat_model
from langchain_core.messages import HumanMessage
from langgraph.graph.state import CompiledStateGraph

from src.agents.code import CodeActState, create_codeact
from src.config import llm_settings


def eval(code: str, _locals: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    # Add project root to sys.path so imports work correctly
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    
    # Store original keys before execution
    original_keys = set(_locals.keys())

    try:
        with contextlib.redirect_stdout(io.StringIO()) as f:
            exec(code, builtins.__dict__, _locals)
        result = f.getvalue()
        if not result:
            result = "<code ran, no output printed to stdout>"
    except Exception as e:
        result = f"Error during execution: {repr(e)}"

    # Determine new variables created during execution
    new_keys = set(_locals.keys()) - original_keys
    new_vars = {key: _locals[key] for key in new_keys}
    return result, new_vars


llm: BaseChatModel = init_chat_model(
    model=llm_settings.model_name,
    model_provider="openai",
    api_key=llm_settings.api_key,
    base_url=llm_settings.base_url,
    temperature=llm_settings.temperature,
)


# agent: CompiledStateGraph[Any, None, Any, Any] = create_codeact(
#     model=llm,
#     eval_fn=eval,
# ).compile()

# # analyze_price_trend
# state: CodeActState = CodeActState(
#     # messages=[HumanMessage(content="你有什么技能？参照技能计算一下sin（325）-cos（32135）")],
#     messages=[HumanMessage(content="我想分析一下股票的涨跌趋势，请帮我分析一下股票000001")],
#     script=None,
#     tool_command=None,
#     context={},
#     remaining_steps=20,
#     execution_summary=None,
# )


# for chunk in agent.stream(input=state, stream_mode="values"):
#     chunk["messages"][-1].pretty_print()
