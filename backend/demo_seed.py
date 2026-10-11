"""演示数据填充脚本: 知识库文档 + SQL示例 + 语义层(模型/指标/维度)。

通过平台 API 创建(与前端行为一致), 文档与示例会自动后台向量化入 ChromaDB。
可重复执行(按标题/名称幂等跳过已存在项)。
"""
import sys
import httpx

BASE = "http://localhost:8004/api/v1"
DS_ID = "3c58b522-eb3e-48aa-9ac7-6cc42b4d9278"  # 本地演示库

DOC_1 = """演示库数据字典

一、表清单与用途
1. demo_sales_orders 销售订单事实表: 每行一笔订单, 记录区域、产品、金额、数量与日期。数据范围为最近一年(约430笔)。
2. demo_products 产品维表: 产品名称、所属类别(category, 如智能硬件/家居生活/办公设备)、单价(unit_price)。
3. demo_regions 区域维表: 区域名称(name, 如华东/华南/华北/西南/东北)与区域负责人(manager)。

二、关联关系
- demo_sales_orders.region_id 关联 demo_regions.id
- demo_sales_orders.product_id 关联 demo_products.id
做区域/产品相关分析时需要 JOIN 维表获取名称与类别。

三、重要字段说明
- amount: 订单金额(元), 即销售额的统计口径, 含商品总价, 不含运费与退款。
- quantity: 本笔订单购买件数。
- order_date: 下单日期(按自然日记录), 时间分析默认按此字段。
"""

DOC_2 = """销售分析常用思路与口径

一、核心指标口径
- 销售额 = SUM(demo_sales_orders.amount), 不扣减退款。
- 订单数 = COUNT(订单行数)。
- 客单价(平均订单金额) = SUM(amount)/COUNT(订单数), 等价于 AVG(amount)。
- 销售件数 = SUM(quantity), 注意与订单数区分。

二、典型问法与SQL思路
- 排名类(如"各区域销售额排名"): GROUP BY 维度 + ORDER BY 汇总值 DESC, 配合 LIMIT。
- 趋势类(如"每月销售额"): 按日期分组, 月份用 to_char(order_date,'YYYY-MM')。
- 占比类(如"各品类销售额占比"): 先分组汇总, 再除以总计(窗口函数或子查询)。
- 针对某类别/区域的问题: 用 WHERE 过滤维表字段, 需先 JOIN 对应维表。

三、注意事项
- 类别与区域名称在维表中, 事实表只有外键, 直接查询只有编号时请检查是否漏了 JOIN。
- 查询大范围日期时建议在问题中明确时间范围, 如"最近3个月"。
"""

SQL_EXAMPLES = [
    ("各区域经理的团队销售额",
     'SELECT r.manager AS "区域经理", SUM(o.amount) AS "销售额" FROM demo_sales_orders o JOIN demo_regions r ON o.region_id = r.id GROUP BY r.manager ORDER BY "销售额" DESC LIMIT 1000',
     "按区域负责人汇总团队销售额", ["区域", "经理", "排名"]),
    ("每月销售额趋势",
     "SELECT to_char(o.order_date, 'YYYY-MM') AS \"月份\", SUM(o.amount) AS \"销售额\" FROM demo_sales_orders o GROUP BY 1 ORDER BY 1 LIMIT 1000",
     "按自然月汇总销售额, 适合趋势图", ["趋势", "月度"]),
    ("销售额最高的前5个产品",
     'SELECT p.product_name AS "产品", SUM(o.amount) AS "销售额" FROM demo_sales_orders o JOIN demo_products p ON o.product_id = p.id GROUP BY p.product_name ORDER BY "销售额" DESC LIMIT 5',
     "产品销售额TOP5", ["TOP", "产品", "排名"]),
    ("平均订单金额是多少",
     'SELECT AVG(o.amount) AS "平均订单金额", COUNT(*) AS "订单数" FROM demo_sales_orders o LIMIT 1000',
     "计算整体客单价与订单数", ["客单价", "平均"]),
    ("智能硬件品类每个月的销售额",
     "SELECT to_char(o.order_date, 'YYYY-MM') AS \"月份\", SUM(o.amount) AS \"销售额\" FROM demo_sales_orders o JOIN demo_products p ON o.product_id = p.id WHERE p.category = '智能硬件' GROUP BY 1 ORDER BY 1 LIMIT 1000",
     "单品类月度销售趋势, 演示维表过滤", ["类别", "趋势"]),
    ("各区域的订单量和销售额汇总",
     'SELECT r.name AS "区域", COUNT(*) AS "订单数", SUM(o.amount) AS "销售额", SUM(o.quantity) AS "销售件数" FROM demo_sales_orders o JOIN demo_regions r ON o.region_id = r.id GROUP BY r.name ORDER BY "销售额" DESC LIMIT 1000',
     "多指标并列的区域汇总", ["汇总", "多指标"]),
]

METRICS = [
    ("total_amount", "总销售额", "SUM(o.amount)", "decimal",
     ["销售额", "销售收入", "营收", "GMV"], ["region_name", "category", "order_date"]),
    ("order_count", "订单数", "COUNT(*)", "integer",
     ["订单量", "交易笔数", "单量"], ["region_name", "category", "order_date"]),
    ("total_quantity", "销售件数", "SUM(o.quantity)", "integer",
     ["销量", "件数", "卖出多少件"], ["category", "product_name", "order_date"]),
    ("avg_order_value", "平均订单金额", "AVG(o.amount)", "decimal",
     ["客单价", "均价", "单均金额"], ["region_name", "category"]),
    ("region_cover", "覆盖区域数", "COUNT(DISTINCT o.region_id)", "integer",
     ["几个区域", "区域覆盖"], ["order_date"]),
]

DIMENSIONS = [
    ("order_date", "订单日期", "订单下单日期, 可按日/月聚合", "order_date", "date", 2, ["日期", "时间", "月份"]),
    ("region_name", "销售区域", "订单所属销售区域, 来自 demo_regions.name", "region_id", "varchar", 1, ["区域", "大区", "地区"]),
    ("category", "产品类别", "商品所属品类, 来自 demo_products.category", "product_id", "varchar", 1, ["品类", "分类", "类别"]),
    ("product_name", "产品名称", "具体商品, 来自 demo_products.product_name", "product_id", "varchar", 0, ["商品", "单品", "产品"]),
]


def main():
    c = httpx.Client(base_url=BASE, timeout=60)
    r = c.post("/auth/login", json={"username": "admin", "password": "Admin@2026"})
    r.raise_for_status()
    token = r.json()["data"]["access_token"]
    c.headers["Authorization"] = f"Bearer {token}"
    print("login ok")

    # 1. 知识库文档(幂等)
    existing_docs = c.get("/knowledge/docs").json()["data"]
    have_titles = {d["title"] for d in existing_docs}
    for title, doctype, content in [
        ("演示库数据字典", "document", DOC_1),
        ("销售分析常用思路与口径", "document", DOC_2),
    ]:
        if title in have_titles:
            print(f"doc skip: {title}")
            continue
        r = c.post("/knowledge/docs", json={
            "title": title, "doc_type": doctype, "content": content, "datasource_id": DS_ID,
        })
        r.raise_for_status()
        print(f"doc created: {title}")

    # 2. SQL 示例(幂等)
    existing_ex = {e["question"] for e in c.get("/knowledge/sql-examples").json()["data"]}
    for q, sql, desc, tags in SQL_EXAMPLES:
        if q in existing_ex:
            print(f"example skip: {q}")
            continue
        r = c.post("/knowledge/sql-examples", json={
            "question": q, "sql_content": sql, "description": desc,
            "datasource_id": DS_ID, "tags": tags,
        })
        r.raise_for_status()
        print(f"example created: {q}")

    # 3. 语义层(模型 + 指标 + 维度, 幂等)
    models = c.get("/semantic/models").json()["data"]
    model = next((m for m in models if m["name"] == "sales_analysis"), None)
    if model:
        print(f"model skip: sales_analysis ({model['id']})")
    else:
        r = c.post("/semantic/models", json={
            "name": "sales_analysis",
            "display_name": "销售订单分析",
            "description": "基于演示库销售订单的语义模型: 汇总销售额/订单/件数等核心指标, 支持按区域、类别、日期分析",
            "datasource_id": DS_ID,
            "base_table": "demo_sales_orders",
        })
        r.raise_for_status()
        model = r.json()["data"]
        print(f"model created: {model['id']}")
    mid = model["id"]

    # 指标/维度列表从模型详情里读(GET /models/{id} 嵌套返回, 无独立列表端点)
    def _load_detail():
        return c.get(f"/semantic/models/{mid}").json()["data"]

    existing_metrics = {m["name"] for m in _load_detail().get("metrics", [])}
    for name, disp, expr, dtype, synonyms, dims in METRICS:
        if name in existing_metrics:
            print(f"metric skip: {name}")
            continue
        r = c.post(f"/semantic/models/{mid}/metrics", json={
            "name": name, "display_name": disp, "description": f"{disp}({expr})",
            "expression": expr, "data_type": dtype, "synonyms": synonyms, "dimensions": dims,
        })
        r.raise_for_status()
        print(f"metric created: {disp}")

    existing_dims = {d["name"] for d in _load_detail().get("dimensions", [])}
    for name, disp, desc, col, dtype, level, synonyms in DIMENSIONS:
        if name in existing_dims:
            print(f"dimension skip: {name}")
            continue
        r = c.post(f"/semantic/models/{mid}/dimensions", json={
            "name": name, "display_name": disp, "description": desc,
            "column_name": col, "data_type": dtype, "hierarchy_level": level, "synonyms": synonyms,
        })
        r.raise_for_status()
        print(f"dimension created: {disp}")

    print("\nALL DONE")


if __name__ == "__main__":
    sys.exit(main())
