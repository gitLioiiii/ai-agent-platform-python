"""全局配置。

智谱 GLM（OpenAI 兼容接口，base-url=https://open.bigmodel.cn/api/paas/v4，glm-4-flash 免费且支持工具调用）。
密钥等敏感项放在项目根目录 .env（不进 git，参考 .env.example），所有值也可用环境变量覆盖。
"""
import os
from pathlib import Path

# 极简 .env 加载（不引第三方依赖）：已存在的环境变量优先，不被覆盖
_env_file = Path(__file__).resolve().parent.parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

# ===== 大模型（智谱 GLM，OpenAI 兼容）=====
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "glm-4-flash")
# 降低随机性，SQL 生成更稳定（与 Java 版一致）
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))

# ===== 数据分析 Agent 参数（对应 Java 版 agent.*）=====
# SQL 报错后，让模型读报错自我纠错的最大重试次数
MAX_SQL_RETRIES = int(os.getenv("MAX_SQL_RETRIES", "3"))
# 单次查询最多返回多少行（防止把大表整张捞出来撑爆上下文）
MAX_ROWS = int(os.getenv("MAX_ROWS", "200"))

# ===== Embedding（RAG 模块，硅基流动 bge-m3，OpenAI 兼容）=====
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "https://api.siliconflow.cn/v1")
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")

# ===== RAG 检索参数（对应 Java 版 rag.*）=====
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "4"))
RAG_SIMILARITY_THRESHOLD = float(os.getenv("RAG_SIMILARITY_THRESHOLD", "0.3"))

# ===== Milvus 向量库（先 docker compose up -d 起来）=====
MILVUS_URI = os.getenv("MILVUS_URI", "http://localhost:19530")
MILVUS_COLLECTION = os.getenv("MILVUS_COLLECTION", "rag_kb")
# bge-m3 输出 1024 维，必须和这里一致
MILVUS_DIM = int(os.getenv("MILVUS_DIM", "1024"))
MILVUS_METRIC = os.getenv("MILVUS_METRIC", "COSINE")
MILVUS_INDEX_TYPE = os.getenv("MILVUS_INDEX_TYPE", "IVF_FLAT")

# ===== 多轮对话记忆 =====
MEMORY_MAX_TURNS = int(os.getenv("MEMORY_MAX_TURNS", "8"))

# ===== MySQL 业务库（复用 Java 版 application.properties 配置）=====
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DB = os.getenv("MYSQL_DB", "ai_agent_demo")
