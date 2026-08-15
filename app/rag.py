"""企业知识库 RAG（Milvus 版）—— 对应 Java 版 KnowledgeBaseServiceImpl。

向量库用 Milvus（docker compose up -d 起 etcd+minio+milvus）：
- ingest：切块 → bge-m3 向量化 → 写入 Milvus 集合
- ask：问题向量化 → Milvus 检索 topK → 相似度阈值过滤 → 命中则「只依据资料」作答 + 引用溯源；未命中则拒答（防幻觉）
"""
import threading

from pymilvus import DataType, MilvusClient

from app.config import (MILVUS_COLLECTION, MILVUS_DIM, MILVUS_INDEX_TYPE,
                        MILVUS_METRIC, MILVUS_URI, RAG_SIMILARITY_THRESHOLD, RAG_TOP_K)
from app.embeddings import embed_query, embed_texts
from app.llm import ask_llm

_lock = threading.Lock()
_client: MilvusClient | None = None

_RAG_SYSTEM = """你是企业知识库问答助手。只能依据下面给出的「已知资料」回答用户问题。
规则：
1. 答案必须来自已知资料，不得编造资料里没有的内容；
2. 如果资料不足以回答，直说「根据现有资料无法确定」，不要硬答；
3. 回答简洁、用中文、直接给结论。"""


def init_store() -> None:
    """连接 Milvus，首次启动自动建集合 + 建索引（对应 Java 版 initialize-schema=true）。"""
    global _client
    _client = MilvusClient(uri=MILVUS_URI)
    if not _client.has_collection(MILVUS_COLLECTION):
        schema = _client.create_schema(auto_id=True, enable_dynamic_field=False)
        schema.add_field("id", DataType.INT64, is_primary=True)
        schema.add_field("vector", DataType.FLOAT_VECTOR, dim=MILVUS_DIM)
        schema.add_field("text", DataType.VARCHAR, max_length=8192)
        schema.add_field("source", DataType.VARCHAR, max_length=512)

        index_params = _client.prepare_index_params()
        index_params.add_index(field_name="vector", index_type=MILVUS_INDEX_TYPE,
                               metric_type=MILVUS_METRIC, params={"nlist": 128})
        _client.create_collection(MILVUS_COLLECTION, schema=schema, index_params=index_params)
    _client.load_collection(MILVUS_COLLECTION)


def _split(text: str, chunk_size: int = 400, overlap: int = 60) -> list[str]:
    """简单切块：先按空行分段，再按长度打包（带重叠），类比 TokenTextSplitter。"""
    paragraphs = [p.strip() for p in text.replace("\r\n", "\n").split("\n") if p.strip()]
    chunks, buf = [], ""
    for p in paragraphs:
        if len(buf) + len(p) + 1 <= chunk_size:
            buf = f"{buf}\n{p}" if buf else p
        else:
            if buf:
                chunks.append(buf)
            if len(p) > chunk_size:
                for i in range(0, len(p), chunk_size - overlap):
                    chunks.append(p[i:i + chunk_size])
                buf = ""
            else:
                buf = p
    if buf:
        chunks.append(buf)
    return chunks or [text]


def ingest(text: str, source: str | None) -> int:
    """把一篇文档切块入库，返回切分片段数。"""
    src = source.strip() if source and source.strip() else "未命名文档"
    chunks = _split(text)
    vectors = embed_texts(chunks)
    rows = [{"vector": vec, "text": chunk, "source": src} for chunk, vec in zip(chunks, vectors)]
    with _lock:
        _client.insert(MILVUS_COLLECTION, rows)
    return len(chunks)


def ask(question: str) -> dict:
    """检索 + 作答。返回 {grounded, answer, sources:[{source,score}], chunks:[...]}。"""
    qv = embed_query(question)
    results = _client.search(
        MILVUS_COLLECTION,
        data=[qv],
        limit=RAG_TOP_K,
        output_fields=["text", "source"],
        search_params={"metric_type": MILVUS_METRIC},
    )
    # COSINE 下 distance 即相似度（越大越相似），按阈值过滤
    hits = [h for h in results[0] if h["distance"] >= RAG_SIMILARITY_THRESHOLD]

    # 拒答：没召回到相关内容，就不硬答（防幻觉）
    if not hits:
        return {"grounded": False, "answer": "知识库里没有找到相关内容，无法回答这个问题。",
                "sources": [], "chunks": []}

    context = ""
    sources, chunks = [], []
    for i, h in enumerate(hits):
        entity = h["entity"]
        context += f"【片段{i + 1}】\n{entity['text']}\n\n"
        sources.append({"source": entity["source"], "score": round(h["distance"], 4)})
        chunks.append(entity["text"])

    answer = ask_llm(_RAG_SYSTEM, f"已知资料：\n{context}问题：{question}")
    return {"grounded": True, "answer": answer, "sources": sources, "chunks": chunks}
