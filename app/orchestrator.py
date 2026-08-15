"""主控 Agent（意图路由）—— 对应 Java 版 OrchestratorServiceImpl。

一个入口 /chat/ask 统一接客：
1. 多轮：有历史就把「那华东呢？」这类问题改写成不依赖上下文的独立问题（指代消解）；
2. 意图分类 DATA / KB / CHAT；
3. 路由到 数据分析 Agent / 知识库 RAG / 闲聊，统一返回 intent+route+answer+detail；
4. 写入会话记忆供下一轮。
"""
from app import memory, rag
from app.agent import run_agent
from app.llm import ask_llm

_REWRITE_SYSTEM = """你是一个「指代消解 / 问题改写」器。根据对话历史，把用户最新的问题改写成一个【不依赖上下文、可独立理解】的完整问题。

要求：
- 只补全省略和指代（如「那」「它」「这个」「呢」），把代词替换成它在上文真正指向的具体实体；
- 严格保持最新问题本身的意图和限定词不变：用户问「华东」就必须是华东，绝不能串成上文的「华南」；时间、地区、指标等实体要对应准确；
- 不要自己回答问题，不要新增上文没有的条件，不要解释；
- 如果最新问题本身已经完整，就原样输出。
只输出改写后的问题，不要解释、不要引号。

示例：
历史：用户：华南区上个月的销售额是多少 / 助手：华南区上月销售额为 120 万。
最新问题：那华东呢？
输出：华东区上个月的销售额是多少？

示例：
历史：用户：年假最多几天 / 助手：满3年10天。
最新问题：那病假呢？
输出：病假的规定是怎样的？"""

_INTENT_SYSTEM = """你是一个意图分类器。判断用户问题属于哪一类，只输出一个词：DATA、KB 或 CHAT。
DATA = 查询业务数据库的统计/数值/排名（销售额、订单数、产品价格、环比、区域销量等）
KB   = 查询公司制度/文档/知识库内容（考勤、年假、报销、规章流程等）
CHAT = 其他闲聊、问候或无法归类
只输出 DATA、KB 或 CHAT 一个词，不要解释、不要标点。"""


def _rewrite(history: str, question: str) -> str:
    try:
        r = ask_llm(_REWRITE_SYSTEM, f"对话历史：\n{history}\n最新问题：{question}")
        return r or question
    except Exception:  # noqa: BLE001
        return question


def _classify(question: str) -> str:
    try:
        label = ask_llm(_INTENT_SYSTEM, question).upper()
        if "DATA" in label:
            return "DATA"
        if "KB" in label:
            return "KB"
        return "CHAT"
    except Exception:  # noqa: BLE001
        return "CHAT"


def chat(question: str, session_id: str | None) -> dict:
    sid = session_id.strip() if session_id and session_id.strip() else "default"
    history = memory.as_text(sid)

    # 1) 多轮指代改写
    standalone = question if not history else _rewrite(history, question)
    # 2) 意图分类
    intent = _classify(standalone)

    resp = {"sessionId": sid, "intent": intent}
    if standalone != question:
        resp["rewritten"] = standalone

    # 3) 路由
    if intent == "DATA":
        resp["route"] = "数据分析 Agent"
        answer, trace = run_agent(standalone)
        resp["detail"] = {"executedSqls": trace["executed_sqls"],
                          "columns": trace["last_columns"], "rows": trace["last_rows"]}
    elif intent == "KB":
        resp["route"] = "知识库 RAG"
        kb = rag.ask(standalone)
        answer = kb["answer"]
        resp["detail"] = {"grounded": kb["grounded"], "sources": kb["sources"], "chunks": kb["chunks"]}
    else:
        resp["route"] = "闲聊"
        prefix = "" if not history else f"对话历史：\n{history}\n"
        answer = ask_llm("你是一个企业 AI 智能体平台的对话助手，礼貌、简洁，用中文回答。",
                         f"{prefix}用户：{question}")

    resp["answer"] = answer

    # 4) 写入会话记忆
    memory.add(sid, "user", question)
    memory.add(sid, "assistant", answer)
    return resp
