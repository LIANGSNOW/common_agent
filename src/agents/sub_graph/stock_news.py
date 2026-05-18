from langgraph.graph import END, START, MessagesState, StateGraph
import json
from pydantic import BaseModel, Field
from langchain_deepseek import ChatDeepSeek
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate
import os
from dotenv import load_dotenv
from tavily import TavilyClient
from datetime import datetime
from urllib.parse import urlparse

load_dotenv()

class News_State(MessagesState):
    stock_code: str
    plan: str
    question: dict
    web_search_news: list[json] | None
    answer: str 
    should_continue: bool
    round: int
    current_subquestion_index: int  # Track current subquestion

class Stock_Code(BaseModel):
    stock_code: str = Field(
        ...,
        description="股票代码, 比如 600000，如果没有提取到，则返回字符串'null' ",
    )

class news_agent:
    def __init__(self):
        self.llm = ChatDeepSeek(
            model="deepseek-chat",
            temperature=1,
            max_tokens=1024,
            timeout=None,
            max_retries=2,
        )
        # Initialize session directory for storing search results
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.search_dir = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'search_cache', session_id)
        os.makedirs(self.search_dir, exist_ok=True)
        self.workflow = self._build_workflow()

    def create_agent(self):
        return self.workflow

    def planner(self,state: News_State):
        messages = state['messages'][-1]
        user_content = messages.content if hasattr(messages, 'content') else str(messages)
        
        news_prompt = """
            你是一个金融研究型 agent，目标是为"股票信息调研"生成用于搜索引擎的高质量查询问题。

            【总体目标】
            根据用户提出的股票相关问题，系统性地拆解出"必须通过搜索引擎获取"的关键信息点，
            并为每个信息点生成清晰、具体、可检索的搜索问题，用于后续的 web search。

            用户问题: {questions}

            【适用场景】
            - 单只股票或多只股票
            - 用户希望了解：当前现状、近期消息、基本面、市场观点、机构判断、潜在风险与预期
            - 不进行价格预测，不给投资建议，只做信息收集与整理

            【你的任务】
            1. 理解用户的核心研究目标（例如：现状了解 / 事件驱动 / 机构观点 / 风险评估）
            2. 将用户问题拆解为 3–6 个「可独立搜索」的子问题
            3. 为每个子问题生成 1–2 条搜索引擎查询语句（query）
            4. 查询语句应尽量具体、专业、可验证，避免模糊或情绪化表达

            【搜索问题设计原则】
            - 优先使用客观、事实型、研究型措辞
            - 尽量包含：公司名 / 股票代码 / 行业 / 时间范围 / 信息类型
            - 倾向于"机构、财报、公告、研究报告、新闻、监管披露"等来源
            - 避免使用"未来一定会""是否值得买"等投资建议导向表述

            【可参考的信息维度（按需选择）】
            - 公司基本面：业务结构、主要收入来源、核心产品
            - 最新事件：公告、并购、财报、监管、诉讼、重大经营变化
            - 财务与业绩：最新财报要点、盈利能力、现金流、负债
            - 行业与竞争：行业趋势、竞争格局、公司所处位置
            - 机构观点：投行/券商/研究机构的评级、观点或分歧
            - 风险因素：已披露风险、市场关注的负面因素、不确定性
            - 市场预期：分析师一致预期、争议点（如有）

            【输出格式要求】
            请严格使用以下 JSON 格式输出，只输出 JSON，不要包含任何其他文字说明：

            {{
            "research_goal": "一句话总结用户希望解决的核心问题",
            "subquestions": [
                {{
                "intent": "该子问题想回答什么",
                "queries": [
                    "搜索引擎查询语句 1",
                    "搜索引擎查询语句 2"
                ]
                }}
            ]
            }}

            【重要限制】
            - 只输出 JSON 格式，不要包含 markdown 代码块标记（如 ```json）
            - 不要回答用户问题本身
            - 不要做分析或下结论
            - 你的唯一输出是"为搜索引擎准备的问题"的 JSON 格式

        """
        
        system_prompt = news_prompt.format(questions=user_content)
        response = self.llm.invoke(system_prompt)
        
        # Extract content from the response message
        response_content = response.content if hasattr(response, 'content') else str(response)
        
        # Try to parse JSON from the response
        try:
            # Remove markdown code blocks if present
            response_content = response_content.strip()
            if response_content.startswith("```"):
                # Remove markdown code block markers
                lines = response_content.split('\n')
                # Remove first line (```json or ```)
                if lines[0].startswith('```'):
                    lines = lines[1:]
                # Remove last line (```)
                if lines and lines[-1].strip() == '```':
                    lines = lines[:-1]
                response_content = '\n'.join(lines)
            
            # Parse JSON
            question_dict = json.loads(response_content)
            
            # Store in state and initialize loop
            return {
                "plan": user_content,
                "question": question_dict,
                "current_subquestion_index": 0,
                "web_search_news": [],
                "messages": [response]
            }
        except json.JSONDecodeError as e:
            print(f"JSON parsing error: {e}")
            print(f"Response content: {response_content}")
            # Fallback: return the raw content
            return {
                "question": {"error": "Failed to parse JSON", "raw_content": response_content},
                "messages": [response]
            }



    def akshare_news():
        pass


    def web_search(self, state: News_State):
        """
        Loop处理每个子问题：
        1. LLM重写子问题（基于意图+上下文，上下文来自messages）
        2. Web搜索获得答案
        3. LLM读取raw_docs总结，结果追加到messages
        """
        question_data = state.get('question', {})
        subquestions = question_data.get('subquestions', [])
        plan = state.get('plan', '')
        messages = state.get('messages', [])
        current_idx = state.get('current_subquestion_index', 0)
        web_search_news = state.get('web_search_news', [])
        
        if current_idx >= len(subquestions):
            return {"should_continue": False, "messages": [AIMessage(content="所有子问题已处理")]}
        
        current_subq = subquestions[current_idx]
        intent = current_subq.get('intent', '')
        original_queries = current_subq.get('queries', [])
        
        print(f'\n[Loop {current_idx+1}/{len(subquestions)}] Intent: {intent}')
        
        # Step 1: LLM重写子问题（用messages作为上下文）
        rewritten_queries = self._rewrite_subquestion(intent, original_queries, messages, plan)
        print(f'[Step 1] Rewritten queries: {rewritten_queries}')
        
        # Step 2: Web搜索 (raw_docs saved to files, evidence is index)
        evidence = self._execute_search(rewritten_queries, current_idx + 1)
        print(f'[Step 2] Found {len(evidence)} documents, saved to {self.search_dir}')
        
        # Step 3: 读取raw_docs，LLM总结并生成message
        summary = self._summarize_to_context(intent, evidence, messages, plan)
        print(f'[Step 3] Summary generated')
        
        # Store evidence index
        web_search_news.append({
            "round": current_idx + 1,
            "intent": intent,
            "queries": rewritten_queries,
            "evidence": evidence,
            "timestamp": datetime.now().isoformat()
        })
        
        next_idx = current_idx + 1
        should_continue = next_idx < len(subquestions)
        
        # 总结作为AIMessage追加到messages（messages是主轴）
        message = AIMessage(content=f"**[Round {current_idx+1}/{len(subquestions)}] {intent}**\n\n{summary}")
        
        return {
            "current_subquestion_index": next_idx,
            "web_search_news": web_search_news,
            "should_continue": should_continue,
            "messages": [message]
        }
    
    def _rewrite_subquestion(self, intent: str, original_queries: list, messages: list, plan: str) -> list:
        """步骤1: 根据意图和messages上下文重写子问题"""
        # 提取最近的messages作为上下文（最多取最近5条AI消息的摘要）
        recent_context = ""
        ai_messages = [m for m in messages if isinstance(m, AIMessage)]
        if ai_messages:
            recent_context = '\n'.join([m.content[:200] for m in ai_messages[-5:]])
        
        prompt = f"""基于上下文重写搜索问题。

【子问题意图】{intent}
【原始查询】{', '.join(original_queries)}
【已有上下文】{recent_context if recent_context else '首次搜索，无上下文'}
【用户需求】{plan}

【任务】生成2-3个精确的搜索查询，JSON格式：{{"queries": ["query1", "query2"]}}
只输出JSON，不要markdown标记。"""
        
        try:
            response = self.llm.invoke(prompt)
            content = response.content.strip()
            if content.startswith('```'):
                content = '\n'.join(content.split('\n')[1:-1])
            result = json.loads(content)
            return result.get('queries', original_queries)
        except:
            return original_queries
    
    def _execute_search(self, queries: list, round_num: int) -> list:
        """步骤2: 执行搜索，raw_docs保存到文件，返回evidence索引"""
        evidence = []
        round_dir = os.path.join(self.search_dir, f"round_{round_num}")
        os.makedirs(round_dir, exist_ok=True)
        
        client = TavilyClient()
        doc_idx = 0
        
        for query in queries:
            try:
                response = client.search(query=query, topic="finance", max_results=5)
                for result in response.get('results', []):
                    doc_idx += 1
                    title = result.get('title', '')
                    url = result.get('url', '')
                    content = result.get('content', '')
                    date = result.get('published_date', 'Unknown')
                    domain = self._extract_domain(url)
                    
                    # Layer 1: Save raw doc to local markdown file
                    file_name = f"doc_{doc_idx:03d}.md"
                    file_path = os.path.join(round_dir, file_name)
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(f"# {title}\n\n")
                        f.write(f"- **URL**: {url}\n")
                        f.write(f"- **Domain**: {domain}\n")
                        f.write(f"- **Date**: {date}\n")
                        f.write(f"- **Query**: {query}\n")
                        f.write(f"- **Score**: {result.get('score', 0)}\n\n")
                        f.write(f"---\n\n{content}\n")
                    
                    # Layer 2: Evidence as index pointing to raw doc
                    evidence.append({
                        "file": file_path,
                        "title": title,
                        "snippet": content[:150].replace('\n', ' '),
                        "url": url,
                        "domain": domain,
                        "date": date
                    })
            except Exception as e:
                print(f"Search error: {e}")
        
        # Save evidence index as markdown
        evidence_path = os.path.join(round_dir, "evidence_index.md")
        with open(evidence_path, 'w', encoding='utf-8') as f:
            f.write(f"# Evidence Index - Round {round_num}\n\n")
            for i, ev in enumerate(evidence, 1):
                f.write(f"## {i}. {ev['title']}\n")
                f.write(f"- **File**: `{os.path.basename(ev['file'])}`\n")
                f.write(f"- **URL**: {ev['url']}\n")
                f.write(f"- **Date**: {ev['date']}\n")
                f.write(f"- **Snippet**: {ev['snippet']}\n\n")
        
        return evidence
    
    def _summarize_to_context(self, intent: str, evidence: list, messages: list, plan: str) -> str:
        """步骤3: 读取raw_docs内容，总结本轮搜索结果"""
        # 读取raw_docs文件内容（每个文件截取前500字）
        raw_contents = []
        for e in evidence[:10]:
            try:
                with open(e['file'], 'r', encoding='utf-8') as f:
                    content = f.read()
                # 跳过metadata header，取正文部分
                if '---\n\n' in content:
                    content = content.split('---\n\n', 1)[1]
                raw_contents.append(f"【{e['title']}】\n{content[:500]}")
            except:
                raw_contents.append(f"【{e['title']}】\n{e['snippet']}")
        
        docs_text = '\n\n'.join(raw_contents)
        
        prompt = f"""根据搜索到的原始文档，针对子问题进行总结。

【子问题】{intent}
【用户需求】{plan}

【搜索到的文档内容】
{docs_text}

【任务】
- 针对子问题，从文档中提取关键信息，生成300-500字的总结
- 标注关键数据、时间、来源
- 直接输出总结文本，不要标题"""
                
        try:
            response = self.llm.invoke(prompt)
            return response.content.strip()
        except Exception as e:
            print(f"Summarize error: {e}")
            return '\n'.join([f"- {e['title']}: {e['snippet']}" for e in evidence[:5]])
    
    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL"""
        try:
            parsed = urlparse(url)
            return parsed.netloc
        except:
            return "unknown"
    
    def should_continue_decision(self, state: News_State):
        """Router: continue loop or end"""
        return "continue" if state.get('should_continue', False) else "end"
    
    def news_collection(self, state: News_State):
        """生成最终报告，基于messages中的累计上下文"""
        plan = state.get('plan', '')
        research_goal = state.get('question', {}).get('research_goal', '')
        messages = state.get('messages', [])
        web_search_news = state.get('web_search_news', [])
        
        # 从messages提取所有轮次的总结（AI messages即为每轮总结）
        round_summaries = '\n\n'.join([
            m.content for m in messages if isinstance(m, AIMessage)
        ])
        
        # 证据列表（用于引用来源）
        all_evidence = []
        for round_data in web_search_news:
            all_evidence.extend(round_data.get('evidence', []))
        sources = '\n'.join([f"- {e['title']} ({e.get('date','Unknown')}) [{e['domain']}]" for e in all_evidence[:30]])
        
        prompt = f"""撰写研究报告。

【需求】{plan}
【目标】{research_goal}

【各轮搜索总结】
{round_summaries}

【信息来源】({len(all_evidence)}条)
{sources}

【要求】Markdown格式，包含：执行摘要、主要发现、信息评估、结论。"""
        
        try:
            response = self.llm.invoke(prompt)
            report = response.content
            return {"answer": report, "messages": [AIMessage(content=report)]}
        except Exception as e:
            error_msg = f"报告生成错误: {e}"
            return {"answer": error_msg, "messages": [AIMessage(content=error_msg)]}

    def _build_workflow(self):
        """
        Workflow: planner -> web_search (loop) -> news_collection
        """
        stock_builder = StateGraph(News_State)
        
        stock_builder.add_node("planner", self.planner)       
        stock_builder.add_node("web_search", self.web_search)
        stock_builder.add_node("news_collection", self.news_collection)
        
        stock_builder.add_edge(START, "planner")
        stock_builder.add_edge("planner", "web_search")
        stock_builder.add_conditional_edges(
            "web_search",
            self.should_continue_decision,
            {"continue": "web_search", "end": "news_collection"}
        )
        stock_builder.add_edge("news_collection", END)

        return stock_builder.compile()

if __name__ == "__main__":
    print('start')
    news = news_agent().create_agent()
    from langchain_core.messages import HumanMessage

    state: News_State = News_State(
    # messages=[HumanMessage(content="你有什么技能？参照技能计算一下sin（325）-cos（32135）")],
    messages=[HumanMessage(content="""
    我想了解一下和黄金相关的股票，找一个中国A股的股票代码，选一支有代表性的股票,根据它最近的新闻，给我进行该股票的分析
    """)],

    )


    for chunk in news.stream(input=state, stream_mode="values"):
        chunk["messages"][-1].pretty_print()