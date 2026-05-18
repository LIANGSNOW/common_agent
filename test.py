from typing import Any, Awaitable, Callable

from deepagents import CompiledSubAgent
from deepagents.middleware.subagents import SubAgentMiddleware
from langchain.agents import create_agent
from langchain.agents.middleware import TodoListMiddleware
from langchain.chat_models import BaseChatModel
# from langgraph.checkpoint.mongodb.aio import AsyncMongoDBSaver
from langgraph.graph import MessagesState
from langgraph.checkpoint.memory import InMemorySaver
from src.agents.sub_graph.stock_new_agent import news_agent

from src.agents.code import create_codeact
from src.agents.main.prompts import (
    SYSTEM_PROMPT,
    TODO_TOOL_DESCRIPTION,
    TODO_TOOL_PROMPT,
)
from src.agents.main.state import MainState


def create_main_agent(
    checkpointer,
    eval_fn: Callable[[str, dict[str, Any]], Awaitable[tuple[str, dict[str, Any]]]],
    llm: BaseChatModel,
):
    """
    创建main agent 实例.

    Args:
        checkpointer: 检查点保存器
        eval_fn: 代码执行函数
        llm: 语言模型
    Returns:
        agent: main agent 实例
    """

    code_agent = create_codeact(
        model=llm,
        eval_fn=eval_fn,
    )
    news = news_agent().create_agent()

    subagent_code = CompiledSubAgent(
        name="code_agent",
        runnable=code_agent,
        description="用于编写和执行代码以完成任务的子代理。",
    )
    subagent_news = CompiledSubAgent(
        name="news_agent",
        runnable=news,
        description="用于获取股票新闻的子代理，需要提供股票代码，stock_code",
    )

    agent = create_agent(
        system_prompt=SYSTEM_PROMPT,
        model=llm,
        middleware=[
            TodoListMiddleware(
                system_prompt=TODO_TOOL_PROMPT,
                tool_description=TODO_TOOL_DESCRIPTION,
            ),
            SubAgentMiddleware(
                default_model=llm, default_tools=[], subagents=[subagent_code,subagent_news]
            ),
        ],
        # checkpointer=checkpointer,
        state_schema=MainState,
    )
    return agent


if __name__ == "__main__":
    import asyncio
    import builtins
    import contextlib
    import io
    import sys
    from pathlib import Path
    from typing import Any
    from langchain.chat_models import BaseChatModel, init_chat_model
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
            
            # Filter out non-serializable objects (functions, classes, modules, etc.)
            def is_serializable(value: Any) -> bool:
                """Check if a value is serializable for checkpointing."""
                import types
                # Exclude functions, methods, classes, modules, and other callables
                if callable(value):
                    return False
                # Exclude types and modules
                if isinstance(value, (type, types.ModuleType)):
                    return False
                # Try to serialize with json to check if it's serializable
                try:
                    import json
                    json.dumps(value)
                    return True
                except (TypeError, ValueError):
                    return False
            
            new_vars = {
                key: _locals[key] 
                for key in new_keys 
                if is_serializable(_locals[key])
            }
            return result, new_vars


    llm: BaseChatModel = init_chat_model(
        model=llm_settings.model_name,
        model_provider="openai",
        api_key=llm_settings.api_key,
        base_url=llm_settings.base_url,
        temperature=llm_settings.temperature,
    )
    def test_agent():
        from langchain.messages import HumanMessage
        from langchain_core.runnables import RunnableConfig


        # handler = get_langfuse_callback_handler(
        #     pk=langfuse_settings.pk,
        #     sk=langfuse_settings.sk,
        #     user_id="user_id",
        #     session_id="session_id",
        # )

        state = MessagesState(
            messages=[
                HumanMessage(
                    "我想分析一下股票的涨跌趋势，请帮我分析一下股票000001,我手里有10万人民币，告诉我应不应该买入,你可以分析一下和这只股票相关的新闻，你只需要给我文字的结论就行"
                ),
            ]
        )
        # from src.main import eval, llm
        # 300750


        checkpointer = InMemorySaver()
        agent = create_main_agent(checkpointer, eval, llm)
        for chunk in agent.stream(
                input=state,
                stream_mode=["values"],
                config=RunnableConfig(
                    configurable={"thread_id": "234234", "user_id": "werwerwr"},
                    recursion_limit=50,
                ),
                subgraphs=True,
            ):
                chunk[-1]["messages"][-1].pretty_print()

    # asyncio.run(test_agent())
    test_agent()
