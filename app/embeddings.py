"""Embedding 客户端 —— 复用 Java 版硅基流动 bge-m3（OpenAI 兼容 /v1/embeddings）。

直接用 httpx 调，不依赖 langchain 的 tiktoken 长度校验（bge-m3 不是 OpenAI 模型，
用 OpenAIEmbeddings 会因 tiktoken 编码报错，直连最省事、最可控）。
"""
import httpx

from app.config import EMBEDDING_API_KEY, EMBEDDING_BASE_URL, EMBEDDING_MODEL


def embed_texts(texts: list[str]) -> list[list[float]]:
    """把多段文本批量向量化，返回向量列表（bge-m3 输出 1024 维）。"""
    resp = httpx.post(
        f"{EMBEDDING_BASE_URL}/embeddings",
        headers={"Authorization": f"Bearer {EMBEDDING_API_KEY}"},
        json={"model": EMBEDDING_MODEL, "input": texts},
        timeout=60.0,
    )
    resp.raise_for_status()
    data = resp.json()["data"]
    # 按 index 排序，保证与输入顺序一致
    data.sort(key=lambda d: d["index"])
    return [d["embedding"] for d in data]


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
