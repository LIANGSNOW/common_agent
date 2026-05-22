from langchain.agents import create_agent
from langchain.chat_models import BaseChatModel, init_chat_model
from langgraph.checkpoint.memory import MemorySaver

from src.agents.common.prompts import render_system_prompt
from src.agents.common.state import CommonAgentState
from src.agents.common.tools import build_coordinator_tools


def create_default_model() -> BaseChatModel:
    from src.config import llm_settings

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
    recursion_limit: int = 60,
    checkpointer=None,
):
    selected_model = model or create_default_model()
    used_checkpointer = checkpointer if checkpointer is not None else MemorySaver()
    agent = create_agent(
        model=selected_model,
        tools=build_coordinator_tools(model=selected_model),
        system_prompt=render_system_prompt(),
        state_schema=CommonAgentState,
        checkpointer=used_checkpointer,
    )
    return agent.with_config({"recursion_limit": recursion_limit})
