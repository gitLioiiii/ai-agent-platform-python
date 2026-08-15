"""数据分析 Agent —— 用 LangGraph 实现「意图理解 → 生成SQL → 执行 → 失败自纠错重试 → 出结论」。

对应 Java 版 DataAnalysisAgentServiceImpl 的 ChatClient 工具调用循环，
这里显式画成一张 LangGraph 状态图，Agent 的自主决策与自我纠错更直观、可控（可讲的面试点）：

    START → agent(LLM决策) ──有tool_calls──→ tools(执行SQL) ──┐
                  │                                            │
                  └───────────── 回到 agent ←──────────────────┘
                  │
              无tool_calls（给出结论）→ END
"""
from typing import Annotated, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import START, END, StateGraph
from langgraph.graph.message import add_messages

from app.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_TEMPERATURE, MAX_SQL_RETRIES
from app.db import SCHEMA_DESCRIPTION
from app.tools import execute_query, get_trace, new_trace

_llm = ChatOpenAI(
    model=LLM_MODEL,
    base_url=LLM_BASE_URL,
    api_key=LLM_API_KEY,
    temperature=LLM_TEMPERATURE,
)
_llm_with_tools = _llm.bind_tools([execute_query])
_tool_map = {"execute_query": execute_query}


def _build_system_prompt() -> str:
    return f"""你是一个企业级数据分析助手。用户用自然语言提问，你要通过查询数据库来回答。

可用的数据库表结构（只能用这里出现的真实表和字段，禁止臆造）：
{SCHEMA_DESCRIPTION}

工作流程：
1. 理解用户意图，判断要查哪些表、怎么聚合（求和/计数/分组/排序/同比环比等）；
2. 生成一条标准的 MySQL SELECT 查询；
3. 【必须】调用 execute_query 工具执行这条 SQL —— 唯一获得数据的方式就是调用工具，不要把 SQL 直接写在回答里；
4. 若返回以「错误:」开头，仔细读报错（字段名错、语法错、表名错等），修正 SQL 后重试，最多重试 {MAX_SQL_RETRIES} 次；
5. 拿到工具返回的真实数据后，用简洁中文给出结论：点明关键数字，必要时解读趋势（如环比增长多少）。

铁律（最重要）：
- 在通过 execute_query 拿到真实返回结果之前，绝对不许给出任何具体数字、排名或结论；
- 严禁凭空编造、猜测或假设查询结果；严禁只把一条 SQL 当作最终答案丢给用户；
- 任何涉及数据的问题，都必须先调用 execute_query，哪怕你觉得自己知道答案。

规则（MySQL 方言）：
- 只能查询（SELECT），绝不增删改；
- order_date 是 'YYYY-MM-DD' 文本，涉及「本月/上月/最近N天」用 MySQL 日期函数：
    本月：DATE_FORMAT(order_date, '%Y-%m') = DATE_FORMAT(CURDATE(), '%Y-%m')
    上月：DATE_FORMAT(order_date, '%Y-%m') = DATE_FORMAT(CURDATE() - INTERVAL 1 MONTH, '%Y-%m')
    最近N天：order_date >= DATE_SUB(CURDATE(), INTERVAL N DAY)
- 金额保留两位小数，结果讲人话，不要把原始 SQL 或表结构直接甩给用户。"""


class _State(TypedDict):
    messages: Annotated[list, add_messages]


def _call_model(state: _State) -> dict:
    return {"messages": [_llm_with_tools.invoke(state["messages"])]}


def _tool_node(state: _State) -> dict:
    last = state["messages"][-1]
    outputs = []
    for call in last.tool_calls:
        result = _tool_map[call["name"]].invoke(call["args"])
        outputs.append(ToolMessage(content=result, tool_call_id=call["id"]))
    return {"messages": outputs}


def _should_continue(state: _State):
    last = state["messages"][-1]
    return "tools" if getattr(last, "tool_calls", None) else END


def _build_graph():
    builder = StateGraph(_State)
    builder.add_node("agent", _call_model)
    builder.add_node("tools", _tool_node)
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", _should_continue, {"tools": "tools", END: END})
    builder.add_edge("tools", "agent")
    return builder.compile()


_graph = _build_graph()


def run_agent(question: str) -> tuple[str, dict]:
    """执行一次问答，返回 (自然语言结论, 执行轨迹)。"""
    new_trace()
    messages = [SystemMessage(content=_build_system_prompt()), HumanMessage(content=question)]
    # 每轮 SQL 尝试 = agent + tools 两步；留足 MAX_SQL_RETRIES+1 次尝试 + 最终作答
    limit = 2 * (MAX_SQL_RETRIES + 1) + 2
    result = _graph.invoke({"messages": messages}, config={"recursion_limit": limit})
    answer = result["messages"][-1].content
    return answer, get_trace()
