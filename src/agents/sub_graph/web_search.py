from langgraph.graph import END, START, MessagesState, StateGraph
from pydantic import BaseModel, Field
from langchain_deepseek import ChatDeepSeek
from langchain_core.messages import AIMessage, HumanMessage
from tavily import TavilyClient
from dotenv import load_dotenv
from langgraph.types import Send
from typing import TypedDict, Annotated
import operator
import datetime
import json
import logging

load_dotenv()

logger = logging.getLogger(__name__)


PLANNER_PROMPT = """你是一个研究型 agent，目标是为用户问题生成用于搜索引擎的高质量查询。

【任务】
1. 理解用户的核心研究目标
2. 将问题拆解为 3-6 个可独立搜索的子问题
3. 为每个子问题生成 1-2 条搜索引擎查询

【设计原则】
- 优先客观、事实型、研究型措辞
- 尽量包含：主体名 / 时间范围 / 信息类型
- 避免模糊或情绪化表达

用户问题: {question}
现在的时间：{date}
"""

SUMMARIZE_PROMPT = """根据搜索到的原始文档，针对子问题进行总结。

【子问题】{intent}
【用户需求】{user_query}

【文档内容】
{docs}

【任务】
- 从文档中提取关键信息，生成总结,需要控制长度，专注于子问题和用户需求
- 标注关键数据、时间、来源
- 直接输出总结文本，不要标题
"""

EVALUATE_PROMPT = """
你是 deep research agent 的评估模块。

你的任务不是重新规划整个研究，而是判断当前搜索结果是否已经足够回答用户问题。
如果不足，只针对缺失部分生成少量补充搜索查询。

【用户初始问题】
{question}

【研究计划】
{plan}

【搜索结果】
{search_results}

【现在日期】
{date}

请从以下角度评估：
1. Coverage：是否覆盖用户问题的主要维度
2. Directness：是否直接回答用户问题
3. Evidence quality：来源是否足够可信、具体、新近
4. Conflict：是否存在明显矛盾或需要验证的信息
5. Gaps：是否存在必须补充搜索的信息缺口

重要规则：
- 不要因为还能搜索更多就判定不足；只有影响最终回答质量的缺口才需要继续搜索。
- 不要重新做完整 research plan。
- 如果当前信息基本足够，请 is_sufficient=true，并且 followup_queries 为空。
- 如果不足，请说明缺口，并生成 不超过3个高价值 follow-up search queries。
- follow-up queries 应该具体、可搜索、避免重复已有 queries，内部结构是:
    2. 可独立搜索的子问题(intent)
    3. 为每个子问题生成 1-2 条搜索引擎查询(queries)
"""

REPORT_PROMPT = """撰写研究报告。

【需求】{user_query}
【目标】{research_goal}

【各轮搜索总结】
{summaries}

【信息来源】（{n_sources} 条）
{sources}

【要求】Markdown 格式，包含：执行摘要、主要发现、信息评估、结论。
"""


class SubQuestion(BaseModel):
    intent: str = Field(..., description="该子问题想回答什么")
    queries: list[str] = Field(..., description="搜索引擎查询语句")


class ResearchPlan(BaseModel):
    research_goal: str = Field(..., description="一句话总结用户希望解决的核心问题")
    subquestions: list[SubQuestion]


class ResearchEvaluation(BaseModel):
    is_sufficient: bool = Field(
        ...,
        description="当前搜索结果是否足够回答用户初始问题"
    )
    confidence: str = Field(
        ...,
        description="high / medium / low"
    )
    covered_aspects: list[str] = Field(
        default_factory=list,
        description="当前结果已经覆盖的方面"
    )
    missing_aspects: list[str] = Field(
        default_factory=list,
        description="仍然缺失且影响最终回答质量的方面"
    )
    followup_queries: list[SubQuestion]


class WorkerState(MessagesState):
    subquestion: dict
    user_query: str



class ResearchState(MessagesState):
    user_query: str
    research_plan: dict
    subquestions: list[dict]
    search_results: Annotated[list, operator.add]
    evaluation: dict
    followup_queries: list[dict]
    iteration: int
    answer: str



class research_agent:
    MAX_ROUNDS = 2  # planner 后的首轮 + 最多 MAX_ROUNDS 轮 followup

    def __init__(self):
        self.llm = ChatDeepSeek(
            model="deepseek-chat",
            temperature=1,
            max_tokens=4096,
            timeout=None,
            max_retries=2,
        )
        self.tavily = TavilyClient()
        self.workflow = self._build_workflow()

    def create_agent(self):
        return self.workflow

    def planner(self, state: ResearchState):
        last_msg = state['messages'][-1]
        user_content = last_msg.content if hasattr(last_msg, 'content') else str(last_msg)

        structured = self.llm.with_structured_output(ResearchPlan)
        plan_result = structured.invoke(PLANNER_PROMPT.format(question=user_content, date=datetime.datetime.today()))
        logger.info("research plan: %s", plan_result.model_dump())
        plan_data = plan_result.model_dump()
        return {
            "user_query": user_content,
            "research_plan": plan_data,
            "subquestions": plan_data["subquestions"],
            "search_results": [],
            "evaluation": {},
            "followup_queries": [],
            "iteration": 0,
        }

    def web_search(self, state: WorkerState):
        user_query = state['user_query']
        subquestion = state['subquestion']
        intent = subquestion['intent']
        queries = subquestion['queries']

        logger.info("queries: %s", queries)

        evidence = self._search(queries)
        logger.info("found %d documents", len(evidence))

        summary = self._summarize(intent, evidence, user_query)
        logger.info("summary generated for intent: %s", intent)

        # 摘要后只保留轻量元数据，丢掉原文 content
        sources = [
            {
                "title": e.get("title", ""),
                "url": e.get("url", ""),
                "date": e.get("date", "Unknown"),
                "snippet": e.get("content", "")[:500],
            }
            for e in evidence
        ]

        result = {
            "intent": intent,
            "queries": queries,
            "summary": summary,
            "evidence": sources,
        }

        message = AIMessage(content=f"**{intent}**\n\n{summary}")

        return {
            "search_results": [result],
            "messages": [message],
        }

    def fan_out(self, state: ResearchState):
        return [
            Send("web_search", {"subquestion": sq, "user_query": state["user_query"]})
            for sq in state["subquestions"]
        ]

    def _search(self, queries: list) -> list:
        evidence = []
        for query in queries:
            try:
                response = self.tavily.search(query=query, topic="general", max_results=5)
                for r in response.get('results', []):
                    evidence.append({
                        "title": r.get('title', ''),
                        "url": r.get('url', ''),
                        "content": r.get('content', ''),
                        "date": r.get('published_date', 'Unknown'),
                    })
            except Exception as e:
                logger.warning("search error for '%s': %s", query, e)
        return evidence

    def _summarize(self, intent: str, evidence: list, user_query: str) -> str:
        if not evidence:
            return "本轮未获取到有效文档"
        docs = '\n\n'.join([f"【{e['title']}】\n{e['content']}" for e in evidence[:10]])
        prompt = SUMMARIZE_PROMPT.format(intent=intent, user_query=user_query, docs=docs)
        try:
            return self.llm.invoke(prompt).content.strip()
        except Exception as e:
            logger.warning("summarize error: %s", e)
            return '\n'.join([f"- {ev['title']}" for ev in evidence[:5]])

    def should_continue(self, state: ResearchState):
        evaluation = state.get("evaluation", {})
        followup_queries = state.get("followup_queries", [])
        iteration = state.get("iteration", 0)

        if iteration >= self.MAX_ROUNDS:
            return "report"
        if evaluation.get("is_sufficient") or not followup_queries:
            return "report"
        return "continue"

    def prepare_followup(self, state: ResearchState):
        return {
            "subquestions": state.get("followup_queries", []),
            "iteration": state.get("iteration", 0) + 1,
        }
    
    def evaluate(self, state: ResearchState):
        user_query = state['user_query']
        plan = state['research_plan']

        structured = self.llm.with_structured_output(ResearchEvaluation)
        search_results_for_eval = [
            {
                "intent": r.get("intent", ""),
                "queries": r.get("queries", []),
                "summary": r.get("summary", ""),
                "sources": r.get("evidence", [])[:5],
            }
            for r in state.get("search_results", [])
        ]
        prompt = EVALUATE_PROMPT.format(
            question=user_query,
            plan=json.dumps(plan, ensure_ascii=False, indent=2),
            search_results=json.dumps(search_results_for_eval, ensure_ascii=False, indent=2),
            date=datetime.datetime.today(),
        )
        result = structured.invoke(prompt)
        logger.info("evaluation: %s", result.model_dump())

        return {
            "evaluation": result.model_dump(),
            "followup_queries": [q.model_dump() for q in result.followup_queries],
        }


    def report(self, state: ResearchState):
        user_query = state['user_query']
        research_goal = state['research_plan'].get('research_goal', '')
        messages = state['messages']
        search_results = state['search_results']

        summaries = '\n\n'.join([m.content for m in messages if isinstance(m, AIMessage)])

        if not summaries.strip():
            error = "未收集到任何研究信息"
            return {"answer": error, "messages": [AIMessage(content=error)]}

        all_sources = []
        for r in search_results:
            all_sources.extend(r.get('evidence', []))
        sources = '\n'.join(
            [
                f"- [{s.get('title', '')}]({s.get('url', '')}) ({s.get('date', 'Unknown')})"
                for s in all_sources[:30]
            ]
        )

        prompt = REPORT_PROMPT.format(
            user_query=user_query,
            research_goal=research_goal,
            summaries=summaries,
            n_sources=len(all_sources),
            sources=sources,
        )
        try:
            content = self.llm.invoke(prompt).content
            return {"answer": content, "messages": [AIMessage(content=content)]}
        except Exception as e:
            error = f"报告生成错误: {e}"
            return {"answer": error, "messages": [AIMessage(content=error)]}

    def _build_workflow(self):
        builder = StateGraph(ResearchState)
        builder.add_node("planner", self.planner)
        builder.add_node("web_search", self.web_search)
        builder.add_node("evaluate", self.evaluate)
        builder.add_node("prepare_followup", self.prepare_followup)
        builder.add_node("report", self.report)

        builder.add_edge(START, "planner")
        builder.add_conditional_edges("planner", self.fan_out, ["web_search"])

        builder.add_edge("web_search", "evaluate")
        builder.add_conditional_edges(
            "evaluate",
            self.should_continue,
            {"continue": "prepare_followup", "report": "report"},
        )
        builder.add_conditional_edges("prepare_followup", self.fan_out, ["web_search"])

        builder.add_edge("report", END)

        return builder.compile()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    print('start')
    agent = research_agent().create_agent()
    state: ResearchState = ResearchState(
        messages=[HumanMessage(content="对比 NVIDIA Blackwell B200、AMD MI325X、华为昇腾 910C、Groq LPU v2 这四款 2025-2026 年的 AI 推理芯片，包括：FP8/INT8 算力、HBM 容量与带宽、单卡功耗、tokens/J 能效比、典型推理工作负载（Llama-70B、DeepSeek-V3）下的实测吞吐、以及单位 token 成本。")],
    )
    for chunk in agent.stream(input=state, stream_mode="updates"):
        for node, update in chunk.items():
            if not isinstance(update, dict):
                continue
            msgs = update.get("messages")
            if not msgs:
                continue
            if not isinstance(msgs, list):
                msgs = [msgs]
            print(f"\n---- {node} ----")
            for m in msgs:
                m.pretty_print()
