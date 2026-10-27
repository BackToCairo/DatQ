"""开发环境幂等种子数据: 默认角色/权限、演示数据源、样例表、SQL示例、业务文档。

仅当 app_env=development 时由 main.lifespan 调用; 所有步骤均先检查存在性, 可重复执行。
演示数据源指向本平台的 PostgreSQL 库(前缀 demo_ 的业务样例表),
让系统开箱即可体验完整的 NL2SQL -> 执行 -> 图表 流程。
"""
import logging
import random
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, text, func
from sqlalchemy import create_engine as create_sync_engine

from app.database import async_session_factory
from app.config import settings
from app.models.user import User, Role, UserRole, Permission, RolePermission
from app.models.datasource import Datasource, TableMetadata, ColumnMetadata
from app.models.knowledge import KnowledgeDoc, SqlExample
from app.engines import encrypt_password, sync_schema
from app.services import rag_service

logger = logging.getLogger(__name__)

DEFAULT_ROLES = [
    ("admin", "超级管理员", "拥有系统全部权限"),
    ("analyst", "数据分析师", "可进行问数查询、管理知识库"),
    ("viewer", "只读用户", "仅可进行问数查询"),
]

DEFAULT_PERMISSIONS = [
    ("query:execute", "query", "execute", "执行问数查询"),
    ("datasource:manage", "datasource", "write", "管理数据源"),
    ("knowledge:manage", "knowledge", "write", "管理知识库"),
    ("admin:manage", "system", "admin", "系统管理"),
]

DEMO_DS_NAME = "本地演示库"


async def _seed_roles_permissions(session) -> dict:
    """默认角色/权限 + admin 角色绑定, 返回角色名->Role 映射。"""
    roles = {}
    for name, display, desc in DEFAULT_ROLES:
        role = (await session.execute(select(Role).where(Role.name == name))).scalar_one_or_none()
        if not role:
            role = Role(name=name, display_name=display, description=desc, is_system=True)
            session.add(role)
            await session.flush()
        roles[name] = role

    perms = {}
    for pname, rtype, action, desc in DEFAULT_PERMISSIONS:
        perm = (await session.execute(select(Permission).where(Permission.name == pname))).scalar_one_or_none()
        if not perm:
            perm = Permission(name=pname, resource_type=rtype, action=action, description=desc)
            session.add(perm)
            await session.flush()
        perms[pname] = perm

    # admin 角色绑定全部权限
    admin_role = roles["admin"]
    for perm in perms.values():
        exists = (await session.execute(
            select(RolePermission).where(
                RolePermission.role_id == admin_role.id,
                RolePermission.permission_id == perm.id,
            )
        )).scalar_one_or_none()
        if not exists:
            session.add(RolePermission(role_id=admin_role.id, permission_id=perm.id))

    # 给 admin 用户授予管理员角色
    admin_user = (await session.execute(select(User).where(User.username == "admin"))).scalar_one_or_none()
    if admin_user:
        exists = (await session.execute(
            select(UserRole).where(UserRole.user_id == admin_user.id, UserRole.role_id == roles["admin"].id)
        )).scalar_one_or_none()
        if not exists:
            session.add(UserRole(user_id=admin_user.id, role_id=roles["admin"].id))
        # 若用户尚无任何角色则补授, 避免早期注册用户无权限
        # (不访问 admin_user.roles, 异步会话懒加载会触发 MissingGreenlet)
        role_cnt = (await session.execute(
            select(func.count(UserRole.user_id)).where(UserRole.user_id == admin_user.id)
        )).scalar() or 0
        if role_cnt == 0:
            session.add(UserRole(user_id=admin_user.id, role_id=roles["viewer"].id))

    await session.flush()
    return roles


def _ensure_demo_tables() -> None:
    """在本地库创建演示业务表并灌入样例数据(幂等)。"""
    engine = create_sync_engine(settings.database_url_sync)
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS demo_regions (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(64) NOT NULL,
                    manager VARCHAR(64)
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS demo_products (
                    id SERIAL PRIMARY KEY,
                    product_name VARCHAR(128) NOT NULL,
                    category VARCHAR(64),
                    unit_price NUMERIC(10, 2)
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS demo_sales_orders (
                    id SERIAL PRIMARY KEY,
                    region_id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL,
                    amount NUMERIC(12, 2),
                    quantity INTEGER,
                    order_date DATE
                )
            """))

            region_count = conn.execute(text("SELECT COUNT(*) FROM demo_regions")).scalar()
            if region_count == 0:
                regions = [("华东", "张三"), ("华南", "李四"), ("华北", "王五"), ("西南", "赵六"), ("东北", "钱七")]
                for i, (name, manager) in enumerate(regions, 1):
                    conn.execute(text(
                        "INSERT INTO demo_regions (id, name, manager) VALUES (:i, :n, :m)"
                    ), {"i": i, "n": name, "m": manager})

            product_count = conn.execute(text("SELECT COUNT(*) FROM demo_products")).scalar()
            if product_count == 0:
                products = [
                    ("智能手环Pro", "智能硬件", 399.00), ("无线耳机Air", "智能硬件", 599.00),
                    ("机械键盘K87", "电脑外设", 349.00), ("4K显示器27寸", "电脑外设", 1599.00),
                    ("升降桌1.4m", "办公家具", 1299.00), ("人体工学椅", "办公家具", 899.00),
                    ("编程入门书", "图书音像", 59.00), ("数据分析实战", "图书音像", 89.00),
                ]
                for i, (name, cat, price) in enumerate(products, 1):
                    conn.execute(text(
                        "INSERT INTO demo_products (id, product_name, category, unit_price) "
                        "VALUES (:i, :n, :c, :p)"
                    ), {"i": i, "n": name, "c": cat, "p": price})

            order_count = conn.execute(text("SELECT COUNT(*) FROM demo_sales_orders")).scalar()
            if order_count == 0:
                rng = random.Random(2026)
                today = datetime.utcnow().date()
                rows = []
                for day in range(120):
                    d = today - timedelta(days=day)
                    for _ in range(rng.randint(2, 5)):
                        rows.append({
                            "r": rng.randint(1, 5),
                            "p": rng.randint(1, 8),
                            "q": rng.randint(1, 20),
                            "d": d.isoformat(),
                        })
                for row in rows:
                    price_map = {1: 399, 2: 599, 3: 349, 4: 1599, 5: 1299, 6: 899, 7: 59, 8: 89}
                    amount = float(price_map[row["p"]]) * row["q"] * (1 + rng.uniform(-0.1, 0.1))
                    conn.execute(text(
                        "INSERT INTO demo_sales_orders (region_id, product_id, amount, quantity, order_date) "
                        "VALUES (:r, :p, :a, :q, :d)"
                    ), {**row, "a": round(amount, 2)})
    finally:
        engine.dispose()


async def _seed_demo_datasource(session) -> None:
    """注册演示数据源并同步表结构元数据 + DDL向量化。"""
    exists = (await session.execute(
        select(Datasource).where(Datasource.name == DEMO_DS_NAME)
    )).scalar_one_or_none()
    if exists:
        return

    ds = Datasource(
        name=DEMO_DS_NAME,
        description="平台内置 PostgreSQL 演示库, 含区域/商品/销售订单样例数据",
        db_type="postgresql",
        host=settings.db_host,
        port=settings.db_port,
        database_name=settings.db_name,
        db_schema="public",
        username=settings.db_user,
        password_enc=encrypt_password(settings.db_password),
        pool_size=5,
        pool_timeout=30,
        timeout=30,
        status="active",
        extra_params={"remark": "系统自动创建的开发演示数据源"},
    )
    session.add(ds)
    await session.flush()
    await session.refresh(ds)

    # 同步表结构元数据
    tables_info = await sync_schema(ds)
    demo_tables = [t for t in tables_info if t["table_name"].startswith("demo_")]
    for t in demo_tables:
        tm = TableMetadata(
            datasource_id=ds.id, table_name=t["table_name"], table_comment=t.get("table_comment"),
        )
        session.add(tm)
        await session.flush()
        for c in t["columns"]:
            session.add(ColumnMetadata(table_id=tm.id, **c))

    try:
        await rag_service.index_ddl(str(ds.id), demo_tables)
    except Exception as e:
        logger.warning("演示DDL向量化失败: %s", e)


async def _seed_knowledge(session) -> None:
    """示例SQL + 业务口径文档(存在即跳过)。"""
    ds = (await session.execute(select(Datasource).where(Datasource.name == DEMO_DS_NAME))).scalar_one_or_none()
    ds_id = ds.id if ds else None

    examples = [
        ("各区域销售额排名",
         'SELECT r.name AS "区域", SUM(o.amount) AS "销售额" '
         "FROM demo_sales_orders o JOIN demo_regions r ON o.region_id = r.id "
         'GROUP BY r.name ORDER BY "销售额" DESC LIMIT 1000',
         "按区域汇总订单金额并降序排列"),
        ("每日销售趋势",
         'SELECT o.order_date AS "日期", SUM(o.amount) AS "销售额" '
         "FROM demo_sales_orders o GROUP BY o.order_date ORDER BY o.order_date LIMIT 1000",
         "按日期汇总销售额, 适合趋势图"),
        ("各品类销售额占比",
         'SELECT p.category AS "品类", SUM(o.amount) AS "销售额" '
         "FROM demo_sales_orders o JOIN demo_products p ON o.product_id = p.id "
         'GROUP BY p.category ORDER BY "销售额" DESC LIMIT 1000',
         "按商品品类汇总销售额"),
    ]
    for question, sql_content, desc in examples:
        exists = (await session.execute(
            select(SqlExample).where(SqlExample.question == question)
        )).scalar_one_or_none()
        if exists:
            continue
        ex = SqlExample(question=question, sql_content=sql_content, description=desc,
                        datasource_id=ds_id, status="active")
        session.add(ex)
        await session.flush()
        try:
            await rag_service.index_sql_example(str(ex.id), question, sql_content,
                                                str(ds_id) if ds_id else None)
        except Exception:
            pass

    doc_title = "演示库业务口径说明"
    exists = (await session.execute(
        select(KnowledgeDoc).where(KnowledgeDoc.title == doc_title)
    )).scalar_one_or_none()
    if not exists:
        content = """演示库业务口径说明

demo_sales_orders 为订单事实表: amount 表示订单金额(元), quantity 表示商品数量, order_date 为下单日期。

demo_regions 为区域维表: name 为区域名称(华东/华南/华北/西南/东北), manager 为区域负责人。

demo_products 为商品维表: category 为商品品类(智能硬件/电脑外设/办公家具/图书音像), unit_price 为标准单价。

业务规则: 销售额 = SUM(demo_sales_orders.amount); 订单量 = COUNT(订单id); 客单价 = 销售额/订单量。
"""
        doc = KnowledgeDoc(title=doc_title, doc_type="document", content=content,
                           datasource_id=ds_id, status="processing")
        session.add(doc)
        await session.flush()
        try:
            count = await rag_service.index_document(str(doc.id), doc_title, content,
                                                     str(ds_id) if ds_id else None)
            doc.chunk_count = count
            doc.status = "active"
        except Exception:
            doc.status = "active"


async def run_seed() -> None:
    """入口: 全部幂等, 失败不阻断应用启动。"""
    _ensure_demo_tables()
    async with async_session_factory() as session:
        await _seed_roles_permissions(session)
        await _seed_demo_datasource(session)
        await _seed_knowledge(session)
        await session.commit()
    logger.info("种子数据检查完成")
