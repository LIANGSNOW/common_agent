"""Simple middleware that asks clarification questions based on user messages.

Flow:
    User message → before_model → should_ask? → Yes → interrupt(question)
                                               → No  → pass through to model
    User answers → graph resumes → answer appended to messages → model runs
"""

from typing import Callable, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage
from langgraph.types import interrupt
from langgraph.types import Command

from langgraph.runtime import Runtime
from langgraph.graph import END
import os
from src.config import llm_settings
from langchain.chat_models import BaseChatModel, init_chat_model

llm: BaseChatModel = init_chat_model(
        model=llm_settings.model_name,
        model_provider="openai",
        api_key=llm_settings.api_key,
        base_url=llm_settings.base_url,
        temperature=llm_settings.temperature,
    )

class QuestionMiddlewareState(AgentState):
    """Compatible with the ThreadState schema."""

    pass


class QuestionMiddleware(AgentMiddleware[QuestionMiddlewareState]):
    """Reads user messages and optionally asks a clarification question before the model runs.

    Usage:
        middleware = QuestionMiddleware(
            should_ask=lambda msgs: len([m for m in msgs if isinstance(m, HumanMessage)]) == 1,
            generate_question=lambda content: f"关于「{content}」，能否补充更多细节？",
        )
    """

    state_schema = QuestionMiddlewareState

    def __init__(
        self,
        *,
        should_ask: Callable[[list], bool] | None = None,
        generate_question: Callable[[str], str] | None = None,
    ):
        """
        Args:
            should_ask: (messages) -> bool, decides whether to interrupt.
                Defaults to asking only on the first user message.
            generate_question: (user_message_content) -> str, builds the question text.
                Defaults to a generic "请补充更多细节" prompt.
        """
        self._should_ask = should_ask
        self._generate_question = generate_question

    def _default_should_ask(self, messages: list) -> bool:
        """Only ask on the very first human message in the conversation."""
        human_count = sum(1 for m in messages if isinstance(m, HumanMessage))
        return human_count == 1

    def _default_generate_question(self, content: str) -> str:
        return f"你提到了「{content}」，能否补充更多细节或具体需求？"

    @override
    def before_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        """Intercept before the LLM runs; optionally pause to ask the user a question."""
        messages = state.get("messages", [])
        if not messages:
            return None

        last_msg = messages[-1]
        if not isinstance(last_msg, HumanMessage):
            return None

        # should_ask = self._should_ask or self._default_should_ask
        # if not should_ask(messages):
        #     return None

        generate_q = self._generate_question or self._default_generate_question
        prompt = """
        我需要你根据用户的内容，提出3个问题，让用户进行选择，来确认具体的问题走向
        {content}

        """
        # response = llm.invoke(prompt.format(content=last_msg.content))
        # content = response.content.strip()
        question = generate_q(last_msg.content)
        # interrupt() pauses graph execution and sends `question` to the caller.
        # When the graph is resumed via Command(resume=answer), interrupt() returns the answer.
        answer = interrupt(question)
        # return Command(
        #     update={"messages": [question]},
        #     goto=END,
        # )

        return {"messages": [HumanMessage(content=str(answer))]}
