# 企业智能体平台（Python / FastAPI / LangGraph）

一个 Java / Spring AI 版本的**同款平台**用 Python 栈重写。主控 Agent 统一接客，自动把问题路由到三种能力：

- **Text2SQL 数据分析 Agent**：自然语言问业务数据 → 生成 SQL → 查库 → 出错自我纠错 → 中文结论
- **RAG 知识库问答**：文档入库 → 向量检索 → 只依据资料作答 + 引用溯源 + 未命中拒答（防幻觉）
- **多轮对话**：会话记忆 + 指代改写（「那华东呢？」→「本月华东区销售额多少」）

> 同一平台我另有一套 **Java / Spring AI** 实现。双栈可讲 = 跨语言 AI 应用落地能力。

## 技术栈
- **FastAPI** — Web 接口 + 多 Tab 演示前端
- **LangGraph** — 把数据分析 Agent 的「决策→调工具→纠错」建成显式状态图（可控循环）
- **LangChain（bind_tools）** — 大模型工具调用（Function Calling）
- **智谱 GLM（glm-4-flash）** — 对话/意图分类/改写/RAG 作答（OpenAI 兼容，`temperature=0.1`）
- **硅基流动 bge-m3（1024 维）** — Embedding（OpenAI 兼容 `/v1/embeddings`）
- **Milvus 向量库** — `docker compose up -d` 起 etcd + minio + milvus，bge-m3 1024 维向量检索（对应 Java 版 Milvus 存储）
- **MySQL（pymysql）** — 业务数据库（区域销售/电商示例，`localhost:3306/ai_agent_demo`）；启动自动建库建表灌示例数据

## 架构
```
                       ┌──────────────── 主控 Agent (/chat/ask) ────────────────┐
用户提问 ──► 指代改写(多轮) ──► 意图分类 DATA/KB/CHAT ──► 路由 ──┐               │
                                                                 ▼               │
        ┌──────────────────────┬──────────────────────┬─────────────────┐       │
        ▼                      ▼                      ▼                 会话记忆写回
  数据分析 Agent           知识库 RAG                闲聊               (下一轮改写用)
  (LangGraph:              (bge-m3 检索             (带历史上下文)
   agent⇄tools 循环         → 拒答/引用溯源
   +只读SQL沙箱)            → 只依据资料作答)
```

## 核心设计（面试点）
1. **主控意图路由**：LLM 分类 DATA/KB/CHAT，一个入口分发到三种 Agent 能力。
2. **Text2SQL Agent Loop 自纠错**：SQL 出错 → 工具返回「错误:…」→ 模型读报错改写重试（LangGraph `recursion_limit` 兜底防死循环）；只读 SQL 沙箱（拦增删改/DDL、自动补 LIMIT）。
3. **RAG 防幻觉**：向量检索 topK + 相似度阈值过滤，未命中直接拒答；命中则「只依据已知资料作答」并回传引用来源与相似度。
4. **多轮指代消解**：按 sessionId 存会话，改写器把省略/代词补成独立问题，严格保持限定词不串味。

## 运行
```bash
docker compose up -d                       # 起 Milvus（etcd + minio + milvus），知识库 RAG 依赖它
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --port 8200 --reload
# 浏览器打开 http://localhost:8200
```
配置在 `app/config.py`，密钥放项目根目录 `.env`：复制 `.env.example` 为 `.env`，填入智谱 / 硅基流动 API Key 和 MySQL 密码（`.env` 不进 git），也可用环境变量覆盖。
> 需本机 MySQL 在跑（`localhost:3306`，库 `ai_agent_demo`）；库/表不存在会在启动时自动创建并灌示例数据。
> 知识库 RAG 依赖 Milvus，须先 `docker compose up -d`（`MILVUS_URI` 默认 `http://localhost:19530`）；只用 Text2SQL / 闲聊可不起 Milvus。

## 接口
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/chat/ask` | 主控：自动意图路由 + 多轮 `{"question","sessionId"}` |
| POST | `/agent/ask` | 直连数据分析 Agent（Text2SQL）`{"question"}` |
| POST | `/kb/ingest` | 知识库入库 `{"text","source"}` |
| POST | `/kb/ask` | 知识库问答 `{"question"}` |

## 目录

```
app/
  config.py        模型/Embedding/RAG/记忆 配置
  db.py            MySQL 示例电商库（pymysql，自动建库建表）+ schema 注入文本
  tools.py         只读 SQL 查询工具（安全校验 + 执行轨迹）
  agent.py         LangGraph 状态机（数据分析 Agent）
  embeddings.py    bge-m3 向量化（硅基流动）
  rag.py           Milvus 向量库 + 入库/检索/拒答/引用
  memory.py        多轮会话记忆
  orchestrator.py  主控 Agent：改写 + 意图分类 + 路由
  llm.py           共享纯对话 LLM
  main.py          FastAPI 入口
static/index.html  多 Tab 演示前端（智能问答 + 知识库管理）
```
