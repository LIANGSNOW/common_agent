
import akshare as ak
from typing import Annotated

from typing_extensions import TypedDict
from langchain_openai import ChatOpenAI
from langgraph.graph.message import add_messages
import os
from langchain_deepseek import ChatDeepSeek
import json
from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from IPython.display import Image, display
from tavily import TavilyClient
from langgraph.graph import END, START, MessagesState, StateGraph
from langchain.messages import AIMessage, HumanMessage, SystemMessage
from datetime import datetime
from langgraph.managed.is_last_step import RemainingSteps


# from model.prophet_stock import predict
from pydantic import BaseModel, Field
load_dotenv()

class News_State(MessagesState):
    stock_code: str
    plan: str
    question: dict
    web_search_news: list[json] |None
    answer: str 
    should_continue: bool
    remaining_steps: RemainingSteps
    round : int

class Stock_Code(BaseModel):
    stock_code: str = Field(
        ...,
        description="the stock code of the company.",
    )

class Stock_News_Answer(BaseModel):
    questions: dict = Field(
        ...,
        description="""用于搜索股票信息的问题. 
                json格式：
                \"questions_en\": [\n",]""",
    )
    question_reason: str = Field(
        ...,
        description="总结为什么要提这些问题，不要以json格式输出，要以普通的文本格式（markdown）输出。",
    )
    should_continue: bool = Field(
        ...,
        description="是否应该继续生成问题进行搜索，补充缺失的信息.",
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
        self.workflow = self._build_workflow()
    
    def create_agent(self):
        return self.workflow
    
    def analysis_question(self, state: News_State):
        messages = state['messages'][-1]
        prompt = """
        你需要做的是提取用户信息中的股票代码
        用户信息:
        {user_info}
        """
        system_prompt = prompt.format(user_info=messages)
        
        response = self.llm.with_structured_output(Stock_Code).invoke(system_prompt)
        stock_code = response.stock_code
        try:
            stock_news_em_df = ak.stock_news_em(symbol=stock_code)
            news = stock_news_em_df[['新闻标题', '新闻内容','发布时间']].to_json(orient='records', force_ascii=False)
        except Exception as e:
            print(e)
            news = None

        question_analysis_prompt = ChatPromptTemplate.from_template(
            """你是一个A股股票分析专家，根据提供的股票分析计划，思考需要获取哪些信息，并生成你想通过搜索引擎获得的问题,
            你需要考虑时效性，我会告诉你现在的日期:{current_date}
            搜索问题不超过三个，并且把问题翻译成英文
            股票分析计划:
            {plan}
            
            请返回一个json格式的数据，包含你想要获取的信息。
            json格式：
                \"questions_en\": [\n",]
            """)

        question_chain = question_analysis_prompt | self.llm | JsonOutputParser()
        question:AIMessage = question_chain.invoke({ "plan": messages, "current_date": datetime.now().strftime("%Y-%m-%d")})

        # response: AIMessage
        return {"stock_code": response.stock_code, "plan": messages,"news": news,"web_search_news":[],"question": question,"messages":[json.dumps(question)]}
    
    def web_search(self, state: News_State):
        question = state['question']
        questions = question['questions_en']
        result_json = dict()
        client = TavilyClient()
        print('start searching')

        for question in questions:
            response = client.search(
                query=question,
                topic="finance",
                include_answer="advanced"
            )
            result_json[question] = response['results']
        print('finish searching')
        web_search_news = state.get('web_search_news', [])
        print(web_search_news)
        web_search_news.append(result_json)
        return {"web_search_news": web_search_news,"messages":[HumanMessage(content=web_search_news)]}

    def news_analyze(self, state: News_State):
        news = state.get('news', [])
        web_search_news = state.get('web_search_news', [])
        plan = state['plan']
        round = state.get("round", 0)
        # Convert to JSON strings to ensure valid JSON format
        news_str = news if isinstance(news, str) else json.dumps(news, ensure_ascii=False, indent=2)
        web_search_news_str = json.dumps(web_search_news, ensure_ascii=False, indent=2)
        
        news_analysis_prompt = ChatPromptTemplate.from_template(
            """
            你是一名严谨的股票分析师。你的任务是根据输入的新闻，判断这些信息是否已经满足股票分析计划（plan）中的所有信息需求。

            请严格遵循以下步骤：
            1. **逐条检查 plan 中的每个信息需求**，判断是否已被以下任一来源充分覆盖：
            - 原始新闻（news）
            - 搜索获得的新闻（web_search_news）

            2. 如果所有关键问题都已满足（“已回答/可判断”），则：
            - 返回：should_continue = false
            - 不执行“问题原因”部分

            3. 如果存在任意未满足的关键问题，则：
            - 返回：should_continue = true
            - 生成不多于3个新的、高质量、可直接用于搜索引擎的搜索问题（search_query）
            - 生成问题原因，并返回给用户

            ## 二、输入
            - 股票分析计划（plan）：
            {plan}

            - 原始新闻（news）：
            {news}

            - 搜索获得的新闻（web_search_news）：
            {web_search_news}

            ---

            ### 问题原因（question_reason）

            必须包含：

            #### **缺失信息**
            基于现在的新闻资料，哪些信息你认为依然缺失，需要继续搜索。

            #### **提问原因**
            简单描述为什么要提出这些新的问题

            """
        )
        news_answer:AIMessage = self.llm.with_structured_output(Stock_News_Answer).invoke(news_analysis_prompt.format(plan=plan, news=news_str, web_search_news=web_search_news_str))
        state["round"] = round + 1
        print(state["round"])
        return {"messages":  news_answer.question_reason,"should_continue": news_answer.should_continue,"question": news_answer.questions}


    def should_continue(self, state: News_State):
        # remaining: RemainingSteps = state.get("remaining_steps")
        round = state.get("round")
        if round is not None and round >2:
            return "news_collection"
        if state['should_continue']:
            return "web_search"
        else:
            return "news_collection"

    def news_collection(self, state: News_State):
        plan = state['plan']
        news = state.get('news', [])
        web_search_news = state.get('web_search_news', [])
        news_collection_prompt = """
            你是一名严谨的股票分析师。你的任务是根据输入的新闻，
            ## 二、输入
            - 股票分析计划（plan）：
            {plan}
            - 原始新闻（news）：
            {news}

            - 搜索获得的新闻（web_search_news）：
            {web_search_news}

            ---

            ### 新闻总结（news_collection）

            必须包含：

            #### **执行摘要**
            基于已获取的信息，简要总结与股票分析相关的关键事实。

            #### **结果与证据**
            引用新闻内容中的具体数据或事实，说明这些证据如何支持股票分析。

            #### **不确定性与局限**
            指出新闻中仍存在的数据缺失或无法确认的部分（如果有）。

            #### **结论**
            总结这些信息可能对该股票产生的潜在影响。
        """
        response = self.llm.invoke(news_collection_prompt.format(plan=plan, news=news, web_search_news=web_search_news))

        return {"messages": [response]}


    def _build_workflow(self):


        stock_builder = StateGraph(News_State)
        stock_builder.add_node("analysis_question", self.analysis_question)
        stock_builder.add_node("web_search", self.web_search)
        stock_builder.add_node("news_analyze", self.news_analyze)
        stock_builder.add_node("news_collection", self.news_collection)

        

        
        
        stock_builder.add_edge(START, "analysis_question")
        stock_builder.add_edge("analysis_question", "web_search")
        stock_builder.add_edge("web_search", "news_analyze")
        stock_builder.add_conditional_edges(
            source="news_analyze",
            path=self.should_continue,
            path_map={"web_search": "web_search", "news_collection": "news_collection"}
        )
        stock_builder.add_edge("news_collection", END)


        return stock_builder.compile()
    
    def analyze(self, stock_code: str):
        return self.workflow.invoke({"stock_code": stock_code})



if __name__ == "__main__":
    print('start')
    news = news_agent().create_agent()
    from langchain_core.messages import HumanMessage

    state: News_State = News_State(
    # messages=[HumanMessage(content="你有什么技能？参照技能计算一下sin（325）-cos（32135）")],
    messages=[HumanMessage(content="""   # 请帮我获取股票代码000001（平安银行）的相关新闻。需要：
    # 1. 最近1个月内的相关新闻
    # 2. 重点关注公司公告、业绩报告、行业政策等
    # 3. 分析新闻对股价的潜在影响
    # 4. 识别正面和负面新闻因素
    # 5. 提供新闻摘要和关键信息点""")],

    )


    for chunk in news.stream(input=state, stream_mode="values"):
        chunk["messages"][-1].pretty_print()
    # stock_code = '000001'
    # stock_news_em_df = ak.stock_news_em(symbol=stock_code)

    # stock_news_em_df = ak.stock_news_em(symbol="603777")
    # print(stock_news_em_df)
