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
load_dotenv()


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

REWRITE_PROMPT = """基于上下文重写搜索问题，生成 2-3 个精确的搜索查询。

【子问题意图】{intent}
【原始查询】{queries}
【已有上下文】{context}
【用户需求】{user_query}
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


class Queries(BaseModel):
    queries: list[str]

class WorkerState(MessagesState):
    subquestion: dict
    user_query: str

class ResearchState(MessagesState):
    user_query: str
    research_plan: dict
    subquestions:list[dict]
    search_results: Annotated[list, operator.add]
    current_index: int
    answer: str


class research_agent:
    def __init__(self):
        self.llm = ChatDeepSeek(
            model="deepseek-chat",
            temperature=1,
            max_tokens=1024,
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
        print(plan_result)
        plan_data = plan_result.model_dump()
        return {
            "user_query": user_content,
            "research_plan": plan_data,
            "subquestions": plan_data["subquestions"],
            "current_index": 0,
            "search_results": [],
        }

    def web_search(self, state: WorkerState):
        user_query = state['user_query']
        subquestion = state['subquestion']
        intent = subquestion['intent']
        queries = subquestion['queries']


        # queries = self._rewrite(intent, original_queries, messages, plan)
        print(f"[Step 1] Rewritten queries: {queries}")

        evidence = self._search(queries)
        print(f"[Step 2] Found {len(evidence)} documents")

        summary = self._summarize(intent, evidence, user_query)
        print(f"[Step 3] Summary generated")

        # search_results.append({
        #     "intent": intent,
        #     "queries": original_queries,
        #     "evidence": evidence,
        # })

        # message = AIMessage(
        #     content=f"**[Round {idx+1}/{len(subquestions)}] {intent}**\n\n{summary}"
        # )

        # return {
        #     "current_index": idx + 1,
        #     "search_results": search_results,
        #     "messages": [message],
        # }
        message = AIMessage(content=f"**{intent}**\n\n{summary}")

        return {
            "search_results": [
                {
                    "intent": intent,
                    "queries": queries,
                    "summary": summary,
                    "evidence": evidence,
                }
            ],
            "messages": [message],
        }

    def fan_out(self,state: ResearchState):
        return [
            Send("web_search", {"subquestion": sq, "user_query": state["user_query"]})
            for sq in state["subquestions"]
        ]
    
    def _rewrite(self, intent: str, original_queries: list, messages: list, user_query: str) -> list:
        ai_messages = [m for m in messages if isinstance(m, AIMessage)]
        context = '\n'.join([m.content[:200] for m in ai_messages[-5:]]) or '首次搜索，无上下文'

        prompt = REWRITE_PROMPT.format(
            intent=intent,
            queries=', '.join(original_queries),
            context=context,
            user_query=user_query,
        )
        try:
            result = self.llm.with_structured_output(Queries).invoke(prompt)
            return result.queries or original_queries
        except Exception as e:
            print(f"Rewrite error: {e}")
            return original_queries

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
                print(f"Search error for '{query}': {e}")
        return evidence

    def _summarize(self, intent: str, evidence: list, user_query: str) -> str:
        if not evidence:
            return "本轮未获取到有效文档"
        docs = '\n\n'.join([f"【{e['title']}】\n{e['content']}" for e in evidence[:10]])
        prompt = SUMMARIZE_PROMPT.format(intent=intent, user_query=user_query, docs=docs)
        try:
            return self.llm.invoke(prompt).content.strip()
        except Exception as e:
            print(f"Summarize error: {e}")
            return '\n'.join([f"- {ev['title']}" for ev in evidence[:5]])

    def should_continue(self, state: ResearchState):
        subquestions = state['research_plan'].get('subquestions', [])
        return "continue" if state['current_index'] < len(subquestions) else "end"

    # def evaluate(self, state: ResearchState):
    #     user_query = state['user_query']
    #     search_results = state['search_results']
    #     prompt = EVALUATE_PROMPT.format(
    #         plan=plan,
    #         search_results='\n\n'.join([json.dumps(r) for r in search_results]),
    #     )
    #     try:
    #         return self.llm.invoke(prompt).content.strip()
    #     except Exception as e:


    def report(self, state: ResearchState):
        user_query = state['user_query']
        research_goal = state['research_plan'].get('research_goal', '')
        messages = state['messages']
        search_results = state['search_results']

        summaries = '\n\n'.join([m.content for m in messages if isinstance(m, AIMessage)])

        if not summaries.strip():
            error = "未收集到任何研究信息"
            return {"answer": error, "messages": [AIMessage(content=error)]}

        all_evidence = []
        for r in search_results:
            all_evidence.extend(r.get('evidence', []))
        sources = '\n'.join(
            [f"- {e['title']} ({e.get('date', 'Unknown')})" for e in all_evidence[:30]]
        )

        prompt = REPORT_PROMPT.format(
            user_query=user_query,
            research_goal=research_goal,
            summaries=summaries,
            n_sources=len(all_evidence),
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
        builder.add_node("report", self.report)

        builder.add_edge(START, "planner")
        builder.add_conditional_edges("planner", self.fan_out, ["web_search"])

        # builder.add_conditional_edges(
        #     "web_search",
        #     self.should_continue,
        #     {"continue": "web_search", "end": "report"},
        # )
        builder.add_edge("web_search", "report")

        builder.add_edge("report", END)

        return builder.compile()


if __name__ == "__main__":
    print('start')
    agent = research_agent().create_agent()
    state: ResearchState = ResearchState(
        messages=[HumanMessage(content="我想了解最近的人工智能发展趋势")],
    )
    for chunk in agent.stream(input=state, stream_mode="values"):
        chunk["messages"][-1].pretty_print()
