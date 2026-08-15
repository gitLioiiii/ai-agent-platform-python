"""FastAPI 入口：企业智能体平台（Python / LangGraph 版）。

主控 Agent + Text2SQL 数据分析 + RAG 知识库 + 多轮对话，一站式。
启动：
    cd "C:\\CODE\\Python AI agent"
    .venv\\Scripts\\python -m uvicorn app.main:app --port 8200 --reload
接口：
    POST /chat/ask    主控：自动意图路由（DATA/KB/CHAT）+ 多轮 {"question","sessionId"}
    POST /agent/ask   直连数据分析 Agent（Text2SQL）
    POST /kb/ingest   知识库入库 {"text","source"}
    POST /kb/ask      知识库问答 {"question"}
    GET  /            演示前端
"""
import os

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import orchestrator, rag
from app.agent import run_agent
from app.db import init_db

app = FastAPI(title="企业智能体平台 (Python/LangGraph)")

_STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")


@app.on_event("startup")
def _startup() -> None:
    # init_db()
    rag.init_store()


class AskRequest(BaseModel):
    question: str


class ChatRequest(BaseModel):
    question: str
    sessionId: str | None = None


class IngestRequest(BaseModel):
    text: str
    source: str | None = None


# 同步 def：Starlette 在线程池执行，阻塞的 LLM 调用不卡事件循环，threading.local 轨迹按请求隔离
@app.post("/chat/ask")
def chat_ask(req: ChatRequest) -> dict:
    return orchestrator.chat(req.question, req.sessionId)


@app.post("/agent/ask")
def agent_ask(req: AskRequest) -> dict:
    answer, trace = run_agent(req.question)
    return {"success": True, "answer": answer, "executedSqls": trace["executed_sqls"],
            "columns": trace["last_columns"], "rows": trace["last_rows"]}


@app.post("/kb/ingest")
def kb_ingest(req: IngestRequest) -> dict:
    count = rag.ingest(req.text, req.source)
    return {"success": True, "chunks": count}


@app.post("/kb/ask")
def kb_ask(req: AskRequest) -> dict:
    return {"success": True, **rag.ask(req.question)}


app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(os.path.join(_STATIC_DIR, "index.html"))
