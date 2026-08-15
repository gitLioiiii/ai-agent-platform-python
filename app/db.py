"""MySQL 示例业务库（区域销售 / 电商风格）。

对应 Java 版 schema.sql + data.sql，连同一个库（ai_agent_demo）：
- 用 pymysql 连 MySQL，配置复用 Java 版 application.properties；
- 订单日期在 Python 里按「当月/上月/上上月」实时生成，保证无论今天几号都能演示「本月/上月/环比」；
- 手写 SCHEMA_DESCRIPTION 注入给模型（比查系统表更清晰，也是 Text2SQL 提准确率的关键手段）。
"""
from datetime import date

import pymysql

from app.config import MYSQL_DB, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USER

# 注入给模型的真实表结构（含中文注释）——schema injection
SCHEMA_DESCRIPTION = """表 region（销售区域）:
  - id (INTEGER) -- 区域ID
  - region_name (TEXT) -- 区域名称，如 华南/华东/华北/西南/西北

表 product（产品）:
  - id (INTEGER) -- 产品ID
  - product_name (TEXT) -- 产品名称
  - category (TEXT) -- 产品品类，如 手机/数码/家电/配件
  - unit_price (REAL) -- 单价(元)

表 sales_order（销售订单）:
  - id (INTEGER) -- 订单ID
  - order_no (TEXT) -- 订单编号
  - region_id (INTEGER) -- 下单区域ID，关联 region.id
  - order_date (TEXT，格式 'YYYY-MM-DD') -- 下单日期
  - total_amount (REAL) -- 订单总金额(元)
  - status (TEXT) -- 订单状态：已完成/已取消/退款

表 order_item（订单明细）:
  - id (INTEGER) -- 明细ID
  - order_id (INTEGER) -- 订单ID，关联 sales_order.id
  - product_id (INTEGER) -- 产品ID，关联 product.id
  - quantity (INTEGER) -- 购买数量
  - amount (REAL) -- 该明细金额(元)
"""

_SCHEMA_STATEMENTS = [
    "DROP TABLE IF EXISTS order_item",
    "DROP TABLE IF EXISTS sales_order",
    "DROP TABLE IF EXISTS product",
    "DROP TABLE IF EXISTS region",
    """CREATE TABLE region (
        id          INT PRIMARY KEY AUTO_INCREMENT,
        region_name VARCHAR(32) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE product (
        id           INT PRIMARY KEY AUTO_INCREMENT,
        product_name VARCHAR(64) NOT NULL,
        category     VARCHAR(32) NOT NULL,
        unit_price   DECIMAL(12,2) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE sales_order (
        id           INT PRIMARY KEY AUTO_INCREMENT,
        order_no     VARCHAR(32) NOT NULL,
        region_id    INT NOT NULL,
        order_date   VARCHAR(10) NOT NULL,
        total_amount DECIMAL(12,2) NOT NULL,
        status       VARCHAR(16) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE order_item (
        id         INT PRIMARY KEY AUTO_INCREMENT,
        order_id   INT NOT NULL,
        product_id INT NOT NULL,
        quantity   INT NOT NULL,
        amount     DECIMAL(12,2) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
]

_REGIONS = ["华南", "华东", "华北", "西南", "西北"]

_PRODUCTS = [
    ("旗舰手机Pro", "手机", 5999.00),
    ("轻薄手机Air", "手机", 3999.00),
    ("智能手表", "配件", 1299.00),
    ("蓝牙耳机", "配件", 699.00),
    ("平板电脑", "数码", 4299.00),
    ("笔记本电脑", "数码", 7999.00),
    ("4K电视", "家电", 4599.00),
    ("变频空调", "家电", 3599.00),
    ("扫地机器人", "家电", 2199.00),
    ("充电宝", "配件", 199.00),
]

# (order_no, region_id, months_ago, day_offset, total_amount, status)
_ORDERS = [
    # 当月（华南偏多，方便演示「本月华南」）
    ("SO-N01", 1, 0, 2, 11998.00, "已完成"),
    ("SO-N02", 1, 0, 4, 3999.00, "已完成"),
    ("SO-N03", 2, 0, 5, 7999.00, "已完成"),
    ("SO-N04", 3, 0, 6, 4599.00, "已完成"),
    ("SO-N05", 4, 0, 7, 3599.00, "已完成"),
    ("SO-N06", 1, 0, 8, 2097.00, "已完成"),
    ("SO-N07", 5, 0, 9, 4299.00, "已取消"),
    # 上月
    ("SO-L01", 1, 1, 3, 5999.00, "已完成"),
    ("SO-L02", 1, 1, 5, 3999.00, "已完成"),
    ("SO-L03", 2, 1, 6, 7999.00, "已完成"),
    ("SO-L04", 3, 1, 8, 2199.00, "已完成"),
    ("SO-L05", 1, 1, 10, 699.00, "已完成"),
    ("SO-L06", 4, 1, 12, 4599.00, "退款"),
    ("SO-L07", 1, 1, 15, 1299.00, "已完成"),
    # 上上月
    ("SO-P01", 2, 2, 4, 7999.00, "已完成"),
    ("SO-P02", 3, 2, 9, 3599.00, "已完成"),
    ("SO-P03", 1, 2, 12, 5999.00, "已完成"),
    ("SO-P04", 5, 2, 14, 199.00, "已完成"),
]

# (order_id, product_id, quantity, amount) —— order_id 与 _ORDERS 插入顺序 1~18 对应
_ITEMS = [
    (1, 1, 2, 11998.00), (2, 2, 1, 3999.00), (3, 6, 1, 7999.00), (4, 7, 1, 4599.00),
    (5, 8, 1, 3599.00), (6, 4, 3, 2097.00), (7, 5, 1, 4299.00), (8, 1, 1, 5999.00),
    (9, 2, 1, 3999.00), (10, 6, 1, 7999.00), (11, 9, 1, 2199.00), (12, 4, 1, 699.00),
    (13, 7, 1, 4599.00), (14, 3, 1, 1299.00), (15, 6, 1, 7999.00), (16, 8, 1, 3599.00),
    (17, 1, 1, 5999.00), (18, 10, 1, 199.00),
]


def _month_start(months_ago: int) -> date:
    """返回「往前 months_ago 个月」那个月的 1 号。"""
    today = date.today()
    idx = today.year * 12 + (today.month - 1) - months_ago
    return date(idx // 12, idx % 12 + 1, 1)


def _order_date(months_ago: int, day_offset: int) -> str:
    ms = _month_start(months_ago)
    return f"{ms.year:04d}-{ms.month:02d}-{day_offset + 1:02d}"


def get_connection() -> pymysql.connections.Connection:
    """连到业务库；返回的游标用 DictCursor（行即 dict，等价原 sqlite3.Row）。"""
    return pymysql.connect(
        host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER, password=MYSQL_PASSWORD,
        database=MYSQL_DB, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def _ensure_database() -> None:
    """库不存在则建（不指定 database 连上去 CREATE DATABASE IF NOT EXISTS）。"""
    conn = pymysql.connect(
        host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER, password=MYSQL_PASSWORD,
        charset="utf8mb4", autocommit=True,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DB}` "
                "DEFAULT CHARACTER SET utf8mb4 DEFAULT COLLATE utf8mb4_general_ci"
            )
    finally:
        conn.close()


def init_db() -> None:
    """每次启动重建示例库（schema 里有 DROP IF EXISTS，与 Java 版 spring.sql.init 行为一致）。"""
    _ensure_database()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for stmt in _SCHEMA_STATEMENTS:
                cur.execute(stmt)
            cur.executemany("INSERT INTO region (region_name) VALUES (%s)",
                            [(r,) for r in _REGIONS])
            cur.executemany(
                "INSERT INTO product (product_name, category, unit_price) VALUES (%s, %s, %s)",
                _PRODUCTS)
            cur.executemany(
                "INSERT INTO sales_order (order_no, region_id, order_date, total_amount, status) "
                "VALUES (%s, %s, %s, %s, %s)",
                [(o[0], o[1], _order_date(o[2], o[3]), o[4], o[5]) for o in _ORDERS])
            cur.executemany(
                "INSERT INTO order_item (order_id, product_id, quantity, amount) VALUES (%s, %s, %s, %s)",
                _ITEMS)
        conn.commit()
    finally:
        conn.close()
