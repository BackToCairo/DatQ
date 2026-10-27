# DatQ 智能问数系统


> 用自然语言查询数据库的 AI 数据分析平台:用中文提问,自动生成 SQL、安全执行、图表可视化,支持知识库增强与多数据源管理。

提问 → NL2SQL 生成 → SQL 安全校验 → 执行 → 表格/图表展示 → CSV 导出,全链路一站式完成。

## 🏗 系统架构

<img width="1792" height="1024" alt="datq-system-architecture_1791681985" src="https://github.com/user-attachments/assets/c4ab3ef8-d559-48fc-b9cb-da083a6ddeff" />

## ✨ 核心特性

- **自然语言问数(NL2SQL)**:接入 OpenAI 兼容协议的大模型(如 DeepSeek、GPT 系列),结合表结构与业务上下文生成可执行 SQL
- **RAG 知识库增强**:内置 ChromaDB 向量库,表结构 DDL、业务口径文档、SQL 示例统一向量化,生成时自动检索注入,口径问题也能答对
- **SQL 安全护栏**:基于 sqlglot 的静态校验——仅允许 SELECT、自动强制 LIMIT、多语句/危险函数拦截、列黑名单与行级权限注入
- **多数据源管理**:支持 MySQL / PostgreSQL / ClickHouse / SQL Server / Oracle / Doris / StarRocks / Redshift / Kingbase 九种数据库,表单按类型自适应(Schema/SSL/Oracle 连接方式/低版本兼容),支持保存前连接探测、线上表结构与字段浏览、表数据预览、按表或全量同步元数据
- **语义层**:语义模型 / 指标 / 维度管理,支持指标同义词(如“营收”“GMV”→销售额)
- **结果可视化**:自动推荐图表(ECharts),表格/图表切换,一键导出 CSV(带 BOM,Excel 中文不乱码)
- **系统管理**:用户、角色、查询日志、操作日志、查询趋势与数据源分布统计
- **优雅降级**:未配置 LLM Key 时自动降级为知识库示例匹配,保证问数链路始终可用


## 🖥 UI 展示

<img width="2549" height="1242" alt="image" src="https://github.com/user-attachments/assets/24ad8c15-0694-4265-9de8-10fba7e09df8" />

<img width="2549" height="1242" alt="image" src="https://github.com/user-attachments/assets/151311b0-548e-47e7-849e-ab6b81c618c4" />

<img width="2549" height="1242" alt="image" src="https://github.com/user-attachments/assets/268f0015-d9e2-44bf-8cb9-5bbaacd510db" />

<img width="2549" height="1242" alt="image" src="https://github.com/user-attachments/assets/5cd88f8b-3ea3-4c9b-9988-dd1b05dedad5" />

<img width="2549" height="1242" alt="image" src="https://github.com/user-attachments/assets/98a858cc-cd8d-411f-9480-4ebd5f965f54" />




## 🚀 快速上手

### 方式一:Docker Compose(推荐)

```bash
# 1. 配置 LLM Key(任选其一即可, 支持所有 OpenAI 兼容服务)
export LLM_API_KEY=sk-xxxxxxxx        # 或在根目录 .env 中配置

# 2. 一键启动(PostgreSQL + Redis + API)
docker compose up -d

# 3. 访问
#   API:        http://localhost:8000
#   API 文档:   http://localhost:8000/docs
```

> 后端默认使用**内嵌 ChromaDB**(数据落盘于容器内目录),compose 中的 `chromadb` 独立服务为可选预留。

### 方式二:本地开发

**前置**:Python 3.11+、Node.js 18+、PostgreSQL 15(创建库 `smart_query`、用户 `smart_query` / 密码 `smart_query_2026`)

```bash
# 1. 后端
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows(PowerShell)
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
cp .env.example .env            # 按需修改, 见下方配置说明
uvicorn app.main:app --port 8004

# 首次启动自动建表 + 写入演示数据(演示数据源 / 样例表 / SQL 示例)
# 追加演示知识库与语义层数据(可选):
python demo_seed.py

# 2. 前端(新终端)
cd frontend
npm install
npm run dev                     # http://localhost:3000, 已代理 /api → 8004
```

打开 http://localhost:3000 ,使用默认账号登录:

| 账号 | 密码 | 角色 |
| --- | --- | --- |
| `admin` | `Admin@2026` | 系统管理员 |

## ⚙️ 配置说明

`backend/.env` 关键配置项:

| 变量 | 说明 | 示例 |
| --- | --- | --- |
| `DB_*` | 元数据库(PostgreSQL)连接 | `DB_HOST=localhost` |
| `JWT_SECRET` | JWT 签名密钥,生产环境务必修改 | 随机字符串 |
| `LLM_API_KEY` | 大模型 API Key(为空则问数走降级匹配) | `sk-xxx` |
| `LLM_BASE_URL` | OpenAI 兼容服务地址 | `https://api.deepseek.com` |
| `LLM_MODEL` | 对话模型 | `deepseek-chat` / `gpt-4o` |
| `LLM_EMBEDDING_ENABLED` | 是否用 LLM 服务做向量化;DeepSeek 无 embeddings 端点需设为 `false`(使用内置本地嵌入) | `true` / `false` |
| `MAX_QUERY_ROWS` | 查询结果行数上限 | `1000` |
| `RATE_LIMIT_QPM` | 每用户每分钟问数限流 | `20` |

## 📁 项目结构

```
DatQ/
├── backend/                 # FastAPI 后端
│   ├── app/
│   │   ├── api/v1/          # REST 接口(auth/query/datasource/knowledge/semantic/admin/...)
│   │   ├── core/            # 认证、依赖注入、限流、异常
│   │   ├── engines/         # 多数据源查询引擎 + SQL 校验器(sqlglot)
│   │   ├── llm/             # NL2SQL(OpenAI 兼容直连 + JSON 健壮解析)
│   │   ├── models/          # SQLAlchemy 模型
│   │   ├── services/        # RAG 服务(ChromaDB 内嵌)等
│   │   └── seed.py          # 启动种子数据(演示库/样例表/示例)
│   ├── tests/               # pytest 冒烟测试
│   └── demo_seed.py         # 演示知识库/语义层数据填充脚本
├── frontend/                # React 18 + TS + Vite 前端
│   └── src/
│       ├── pages/           # Chat/DataSource/Knowledge/Semantic/Dashboard/Admin
│       ├── services/        # axios API 封装
│       └── components/      # 布局等
├── nginx/                   # 生产反向代理配置
├── docker-compose.yml       # 一键编排
└── docs/images/             # README 截图
```

## 📚 API 文档

启动后端后访问 Swagger UI:`http://localhost:8004/docs`(Docker 方式为 `:8000/docs`),共 40+ 个接口,覆盖认证、问数、会话、数据源、知识库、语义层、系统管理。

## 联系我

<img width="880" height="1375" alt="5d04c127c83704fd63cb1f095b22b9eb" src="https://github.com/user-attachments/assets/006121ee-09e2-4111-9b28-6f4cfc8b11fc" />

