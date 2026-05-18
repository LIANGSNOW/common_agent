"""
图服务模块

该模块提供了与图处理引擎交互的核心服务类，主要功能包括：
- 处理用户输入并异步运行图处理流程
- 管理租户上下文和追踪信息
- 集成Langfuse进行会话追踪和回调处理
- 将图输出转换为标准化的聊天响应格式
- 支持流式响应和实时处理

主要类：
    GraphService: 图处理服务的核心类，负责图的执行和响应处理
"""

import logging
import traceback
from typing import List, Optional

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from src.context.tenant import get_tenant_context
from src.context.trace import get_trace_context
from src.models.dto.chat import ChatResponseChunk, ChatResponseMessage
from src.service.langfuse_service import get_langfuse_callback_handler

logger = logging.getLogger(__name__)


class GraphService:
    """
    用于与图处理引擎交互的服务类，
    处理租户上下文和Langfuse追踪。
    """

    def __init__(self, graph) -> None:
        self.trace_id = get_trace_context()
        self.tenant_info = get_tenant_context()
        self.graph = graph

    @staticmethod
    def _get_current_node(chunk) -> str:
        """
        从图的更新块中获取当前节点的名称。

        Args:
            chunk: 图的更新块。

        Returns:
            当前节点的名称。
        """
        return next(iter(chunk), "")

    def _get_config(self, user_id: str, session_id: str) -> RunnableConfig:
        """
        为图运行生成配置字典。

        包含Langfuse回调处理器和唯一的运行ID。

        Args:
            user_id: 启动图运行的用户ID。
            session_id: 当前会话的ID。

        Returns:
            RunnableConfig: 包含Langfuse回调处理器和追踪ID的配置对象。
        """
        if not isinstance(user_id, str) or not user_id:
            logger.warning("警告：user_id应该是一个非空字符串。")
        if not isinstance(session_id, str) or not session_id:
            logger.warning("警告：session_id应该是一个非空字符串。")

        callback_handler = get_langfuse_callback_handler(
            pk=self.tenant_info.langfuse_pk,
            sk=self.tenant_info.langfuse_sk,
            user_id=user_id,
            session_id=session_id,
        )
        return RunnableConfig(
            run_id=self.trace_id,
            callbacks=[callback_handler],
            configurable={"thread_id": session_id, "user_id": user_id},
            recursion_limit=50,
        )

    def _process_chunk(self, chunk, chunk_id: int) -> ChatResponseChunk:
        """
        处理图输出的块并将其转换为ChatResponseChunk格式。

        Args:
            chunk: 图的输出块。
            chunk_id: 当前块的ID。

        Returns:
            ChatResponseChunk: 格式化的聊天响应块。
        """
        node_name: str = self._get_current_node(chunk[0])
        content = ""
        role = "ai"
        is_last_step = False
        is_interrupt = False

        if node_name == "__interrupt__":
            is_interrupt = True
            content = chunk[1][node_name][0].value
        else:
            chunk_type = chunk[1]
            chunk_data = chunk[2]

            if chunk_type == "messages":
                message = chunk_data[0]
                content = message.content
                if message.type == "tool":
                    role = message.type
            else:
                content = chunk_data["messages"]
                is_last_step = chunk_data.get("is_last_step", False)
                is_interrupt = chunk_data.get("is_interrupt", False)

        response_message = ChatResponseMessage(role=role, content=content)

        if node_name.startswith("router"):
            node_name = (
                "正在分析您的问题，识别业务场景和关键词，同时快速学习相关背景知识"
            )
        elif node_name.startswith("planner"):
            node_name = "正在根据您的问题，动态规划执行步骤，为您定制解题路线图"
        elif node_name.startswith("coder"):
            node_name = "正在根据解题路线动态实时生成代码，自动处理数据或运行分析"
        elif node_name.startswith("reporter"):
            node_name = "正在生成您的专属报告，并附上图表和建议"
        elif node_name.startswith("fixed_flow"):
            node_name = "正在调用预设的专业工具解决您的问题"
        elif node_name.startswith("followup"):
            node_name = "已完成您的专属报告，正在自动生成您的进一步提问的建议问题清单"
        elif node_name.startswith("coordinator"):
            node_name = "思考中"
        elif node_name.startswith("xlsx_analysis"):
            node_name = "正在分析Excel文件，处理数据并生成可视化图表"
        elif node_name.startswith("context_compression"):
            node_name = "正在理解历史上下文，处理关键信息"

        return ChatResponseChunk(
            chunk_id=chunk_id,
            current_node=node_name,
            content=[response_message],
            is_last_step=is_last_step,
            is_interrupt=is_interrupt,
            is_final=False,
            trace_id=str(self.trace_id),
        )

    async def a_run_graph(
        self,
        auto_accepted_plan: bool,
        user_input: str,
        resume: bool,
        user_id: str,
        session_id: str,
        file_list: Optional[List] = None,
        stream_mode: List = ["messages", "custom"],
    ):
        """
        异步运行图，处理用户输入并流式返回响应。

        Args:
            auto_accepted_plan: 是否自动接受计划。
            user_input: 用户的输入消息。
            resume: 是否恢复执行。
            user_id: 用户的ID。
            session_id: 会话的ID。
            file_list: 文件列表（可选）。
            stream_mode: 流式模式列表。

        Yields:
            str: 格式为"data: {json_data} \n\n"的SSE字符串。
        """
        config = self._get_config(user_id, session_id)
        chunk_id = 0
        enable_background_investigation = True

        if file_list:
            file_list_str = ""
            for i in file_list:
                file_list_str += i["name"] + ","
            user_query = f"请优先根据文件 {file_list_str} 分析处理，完成" + user_input
            enable_background_investigation = False
        else:
            user_query = user_input

        try:
            if resume:
                state = Command(resume=user_input)
            else:
                state = {
                    "messages": [HumanMessage(user_query)],
                    "chat_history": [HumanMessage(user_query)],
                    "auto_accepted_plan": auto_accepted_plan,
                    "enable_background_investigation": enable_background_investigation,
                    "plan_iterations": 0,
                    "current_plan": None,
                    "observations": [],
                    "background_investigation_results": None,
                    "final_report": None,
                    "message_board": None,
                    "file_list": file_list,
                    "locale": "zh-CN",
                }

            async for chunk in self.graph.astream(
                state, stream_mode=stream_mode, config=config, subgraphs=True
            ):
                response_chunk = self._process_chunk(chunk, chunk_id)
                yield f"data: {response_chunk.model_dump_json()} \n\n"
                chunk_id += 1

            final_chunk = ChatResponseChunk(
                chunk_id=chunk_id,
                current_node="END",
                content=[],
                is_final=True,
                trace_id=str(self.trace_id),
            )
            yield f"data: {final_chunk.model_dump_json()} \n\n"

        except Exception as e:
            logger.error(
                f"图执行过程中发生错误: {e}\n堆栈跟踪:\n{traceback.format_exc()}"
            )


# if __name__ == "__main__":
#     from src.graph import build_graph
#     from src.api.depends.checkpoint.checkpoint_depends import get_async_mongodb_ckpt
#     import asyncio

#     async def main():
#         async for ckpt in get_async_mongodb_ckpt():
#             graph = build_graph(checkpoint=ckpt)
#             test_service = GraphService(graph)
#             state = {
#                 "messages": [
#                     HumanMessage(
#                         "问题示例：1 帮我做一个仓网规划  2 我如何进行仓网结构优化  3 我想要做仓网仿真"
#                     )
#                 ],
#                 "chat_history": [
#                     HumanMessage(
#                         "问题示例：1 帮我做一个仓网规划  2 我如何进行仓网结构优化  3 我想要做仓网仿真"
#                     )
#                 ],
#                 "auto_accepted_plan": True,
#                 "enable_background_investigation": False,
#                 "plan_iterations": 0,
#                 "current_plan": None,
#                 "observations": [],
#                 "background_investigation_results": None,
#                 "final_report": None,
#                 "message_board": None,
#                 "file_list": None,
#                 "locale": "zh-CN",
#             }
#             test_service.a_run_graph()