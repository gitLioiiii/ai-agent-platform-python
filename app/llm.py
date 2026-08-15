"""共享的纯对话大模型（不绑工具）——供 RAG 作答、意图分类、指代改写、闲聊使用。"""
from langchain_openai import ChatOpenAI

from app.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_TEMPERATURE

chat_llm = ChatOpenAI(
    model=LLM_MODEL,
    base_url=LLM_BASE_URL,
    api_key=LLM_API_KEY,
    temperature=LLM_TEMPERATURE,
)


def ask_llm(system: str, user: str) -> str:
    """一问一答的便捷封装，返回纯文本。"""
    from langchain_core.messages import HumanMessage, SystemMessage
    resp = chat_llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
    return (resp.content or "").strip()
