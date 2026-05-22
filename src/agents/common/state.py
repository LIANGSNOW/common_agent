import operator
from typing import Annotated, Any, Literal

from langgraph.graph import MessagesState
from typing_extensions import NotRequired, TypedDict


class Todo(TypedDict):
    id: str
    content: str
    status: Literal["pending", "in_progress", "completed"]


class CommonAgentState(MessagesState):
    plan: NotRequired[list[Todo]]
    workspace: NotRequired[str]
    dr_findings: Annotated[NotRequired[list[dict[str, Any]]], operator.add]
    codeact_artifacts: Annotated[NotRequired[list[dict[str, Any]]], operator.add]
