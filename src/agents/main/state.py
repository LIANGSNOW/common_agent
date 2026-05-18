from langchain.agents import AgentState


class MainState(AgentState):
    final_report: str | None  # 最终的回答
