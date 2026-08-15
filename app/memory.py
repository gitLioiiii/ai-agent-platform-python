"""多轮对话记忆 —— 对应 Java 版 ConversationMemory。

按 sessionId 存最近若干轮对话（内存版），供主控 Agent 做指代改写与闲聊上下文。
"""
import threading
from collections import defaultdict, deque

from app.config import MEMORY_MAX_TURNS

_lock = threading.Lock()
# sessionId -> deque[(role, content)]，最多存 MEMORY_MAX_TURNS 条
_store: dict[str, deque] = defaultdict(lambda: deque(maxlen=MEMORY_MAX_TURNS))


def add(session_id: str, role: str, content: str) -> None:
    with _lock:
        _store[session_id].append((role, content))


def as_text(session_id: str) -> str:
    with _lock:
        turns = list(_store.get(session_id, ()))
    label = {"user": "用户", "assistant": "助手"}
    return "\n".join(f"{label.get(r, r)}：{c}" for r, c in turns)
