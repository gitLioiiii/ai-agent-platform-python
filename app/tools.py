"""Agent 的「查库工具」——移植 Java 版 SqlQueryTools。

只读安全：仅允许单条 SELECT/WITH，拦截增删改/DDL，自动补 LIMIT，防止把库写坏或全表捞出。
每次提问前调 new_trace() 开一份执行轨迹（含纠错重试的每一条 SQL）与最后结果，
供接口返回给前端展示（对应 Java 版每次 new SqlQueryTools 实例的效果）。
"""
import re
import threading

from langchain_core.tools import tool

from app.config import MAX_ROWS
from app.db import get_connection

# 每个请求一份轨迹：同步接口在线程池各自独立线程执行，threading.local 天然隔离
_local = threading.local()

# 禁止出现的写操作/危险关键字（按整词匹配，避免误伤 created_at 这类字段名）
_FORBIDDEN = [
    "insert", "update", "delete", "drop", "alter", "truncate",
    "create", "replace", "grant", "revoke", "merge", "call", "exec",
    "attach", "detach", "pragma", "vacuum",
]


def new_trace() -> dict:
    trace = {"executed_sqls": [], "last_columns": [], "last_rows": []}
    _local.trace = trace
    return trace


def get_trace() -> dict:
    return getattr(_local, "trace", None) or {"executed_sqls": [], "last_columns": [], "last_rows": []}


def _format_rows(rows: list[dict]) -> str:
    if not rows:
        return "查询成功，但没有匹配的数据（0 行）。"
    lines = [f"查询成功，共 {len(rows)} 行："]
    show = min(len(rows), 50)
    for r in rows[:show]:
        lines.append(str(r))
    if len(rows) > show:
        lines.append(f"...（仅展示前 {show} 行）")
    return "\n".join(lines)


@tool
def execute_query(sql: str) -> str:
    """在业务数据库上执行一条只读 SQL 查询(仅支持 SELECT)，返回查询结果。
    参数 sql：一条标准的 MySQL SELECT 查询语句，必须基于已知的真实表和字段。
    若 SQL 有语法或字段错误，会返回以『错误:』开头的报错信息，你应读懂报错、修正 SQL 后重试。"""
    trace = get_trace()
    cleaned = (sql or "").strip()
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1].strip()
    trace["executed_sqls"].append(cleaned)

    lower = cleaned.lower()
    # —— 只读安全校验（移植 Java 版逻辑）——
    if not (lower.startswith("select") or lower.startswith("with")):
        return "错误: 只允许 SELECT 查询，请改写为查询语句。"
    if ";" in cleaned:
        return "错误: 不允许一次执行多条语句，请只写一条 SELECT。"
    for word in _FORBIDDEN:
        if re.search(r"\b" + word + r"\b", lower):
            return f"错误: 检测到非法操作[{word}]，本工具只支持只读查询。"

    # —— 自动补 LIMIT，防止全表捞出 ——
    final_sql = cleaned if " limit " in lower else f"{cleaned} LIMIT {MAX_ROWS}"

    # —— 执行 ——
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(final_sql)
                columns = [d[0] for d in cur.description] if cur.description else []
                rows = list(cur.fetchall())  # DictCursor：每行已是 dict
        finally:
            conn.close()
        trace["last_columns"] = columns
        trace["last_rows"] = rows
        return _format_rows(rows)
    except Exception as e:  # noqa: BLE001 —— 把报错回传给模型，让它自我纠错
        return f"错误: {e}"
