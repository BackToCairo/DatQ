"""Datasource API routes.

多数据源接入能力(移植自 SQLBot):
- 支持类型清单(前端表单按能力渲染)
- 未保存配置的连接探测 / Schema 拉取
- 已保存数据源的连接测试 / Schema / 线上表结构 / 表数据预览
- 元数据同步(可指定表)与 DDL/CSV 表结构导入
"""
import uuid
import csv
import io
import re
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, UploadFile, File, Query
from sqlalchemy import select, delete as sql_delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.datasource import Datasource, TableMetadata, ColumnMetadata
from app.schemas.schemas import (
    DatasourceCreate, DatasourceResponse, DatasourceUpdate, DatasourceProbe,
    TableMetadataResponse, ColumnMetadataResponse, ApiResponse,
)
from app.core.exceptions import (
    AlreadyExistsException, DatasourceConnectionError, NotFoundException, ValidationException,
)
from app.engines import (
    decrypt_password,
    dispose_engine,
    encrypt_password,
    list_columns as engine_list_columns,
    list_schemas as engine_list_schemas,
    list_tables as engine_list_tables,
    preview_table as engine_preview_table,
    sync_schema as engine_sync_schema,
    test_connection as engine_test_connection,
)
from app.engines.dialects import get_dialect, is_supported, list_dialects, normalize_db_type
from app.services import rag_service

router = APIRouter(prefix="/datasources", tags=["数据源"])


# ========== 内部工具 ==========

def _validate_type(db_type: Optional[str]) -> str:
    normalized = normalize_db_type(db_type)
    if not is_supported(normalized):
        raise ValidationException(f"不支持的数据源类型: {db_type}")
    return normalized


def _validate_schema(db_type: str, schema: Optional[str]) -> Optional[str]:
    if normalize_db_type(db_type) == "dm":
        schema = (schema or "").strip()
        if not schema:
            raise ValidationException("达梦数据源必须指定 Schema / 模式")
    return schema


async def _get_ds(db: AsyncSession, ds_id: uuid.UUID) -> Datasource:
    ds = (await db.execute(select(Datasource).where(Datasource.id == ds_id))).scalar_one_or_none()
    if not ds:
        raise NotFoundException("数据源不存在")
    return ds


def _to_response(ds: Datasource, table_count: int = 0) -> DatasourceResponse:
    resp = DatasourceResponse.model_validate(ds)
    resp.table_count = table_count
    return resp


def _probe_payload(data: DatasourceProbe, stored: Optional[Datasource]) -> DatasourceProbe:
    """探测参数补全: 编辑态未填密码时沿用已保存密码。"""
    password = data.password
    if not password and stored is not None:
        password = decrypt_password(stored.password_enc)
    return data.model_copy(
        update={"password": password or "", "db_type": normalize_db_type(data.db_type)}
    )


async def _sync_metadata(
    db: AsyncSession, ds: Datasource, only_tables: Optional[List[str]] = None
) -> dict:
    """同步表结构并写入元数据表 + 向量库。"""
    tables_info = await engine_sync_schema(ds, only_tables)
    tables_data = {t["table_name"]: t["columns"] for t in tables_info}
    comments = {t["table_name"]: t.get("table_comment") for t in tables_info}
    imported = await _save_tables_to_db(tables_data, ds.id, db, comments)
    ds.last_sync_at = datetime.utcnow()
    ds.status = "active"
    await db.flush()

    try:
        await rag_service.index_ddl(str(ds.id), tables_info)
    except Exception:
        pass
    return {"synced_tables": len(imported), "tables": imported}


# ========== 类型与探测 ==========

@router.get("/types", response_model=ApiResponse)
async def list_datasource_types():
    """支持的数据源类型及其连接能力(前端表单据此渲染字段)。"""
    return ApiResponse(data=list_dialects())


@router.post("/test-connection", response_model=ApiResponse)
async def probe_connection(data: DatasourceProbe, db: AsyncSession = Depends(get_db)):
    """未保存配置时测试连接(表单「测试连接」按钮)。"""
    _validate_type(data.db_type)
    stored = await _get_ds(db, data.ds_id) if data.ds_id else None
    payload = _probe_payload(data, stored)
    try:
        result = await engine_test_connection(payload)
    except Exception as e:
        return ApiResponse(code=1, message=str(e), data={"success": False, "message": str(e)})
    return ApiResponse(data=result, message=result["message"])


@router.post("/schemas", response_model=ApiResponse)
async def probe_schemas(data: DatasourceProbe, db: AsyncSession = Depends(get_db)):
    """未保存配置时拉取可选的 schema/库名。"""
    _validate_type(data.db_type)
    stored = await _get_ds(db, data.ds_id) if data.ds_id else None
    payload = _probe_payload(data, stored)
    try:
        schemas = await engine_list_schemas(payload)
    except Exception as e:
        return ApiResponse(code=1, message=f"获取 Schema 失败: {e}", data=[])
    return ApiResponse(data=schemas)


# ========== 数据源 CRUD ==========

@router.get("", response_model=ApiResponse)
async def list_datasources(
    authorization: str = None,
    db: AsyncSession = Depends(get_db)
):
    """获取数据源列表"""
    result = await db.execute(select(Datasource).order_by(Datasource.created_at.desc()))
    datasources = result.scalars().all()
    counts = dict(
        (await db.execute(
            select(TableMetadata.datasource_id, func.count(TableMetadata.id))
            .group_by(TableMetadata.datasource_id)
        )).all()
    )
    items = [_to_response(ds, counts.get(ds.id, 0)).model_dump() for ds in datasources]
    return ApiResponse(data=items)


@router.post("", response_model=ApiResponse)
async def create_datasource(
    data: DatasourceCreate,
    authorization: str = None,
    db: AsyncSession = Depends(get_db)
):
    """创建数据源"""
    db_type = _validate_type(data.db_type)
    db_schema = _validate_schema(db_type, data.db_schema)
    exists = await db.execute(select(Datasource.id).where(Datasource.name == data.name))
    if exists.scalar_one_or_none():
        raise AlreadyExistsException("数据源名称已存在")

    ds = Datasource(
        name=data.name,
        description=data.description,
        db_type=db_type,
        host=data.host,
        port=data.port or get_dialect(db_type).default_port,
        database_name=(data.database_name or "") if get_dialect(db_type).supports_database else "",
        db_schema=db_schema or None,
        username=data.username or "",
        password_enc=encrypt_password(data.password or ""),
        connect_mode=data.connect_mode or "service_name",
        ssl=bool(data.ssl),
        extra_jdbc=data.extra_jdbc or None,
        low_version=bool(data.low_version),
        timeout=data.timeout,
        pool_size=data.pool_size,
        pool_timeout=data.pool_timeout,
        extra_params=data.extra_params or {},
        status="inactive",
    )
    db.add(ds)
    await db.flush()
    await db.refresh(ds)
    return ApiResponse(data=_to_response(ds).model_dump(), message="创建成功")


@router.get("/{ds_id}", response_model=ApiResponse)
async def get_datasource(ds_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """获取数据源详情"""
    ds = await _get_ds(db, ds_id)
    count = (await db.execute(
        select(func.count(TableMetadata.id)).where(TableMetadata.datasource_id == ds_id)
    )).scalar() or 0
    return ApiResponse(data=_to_response(ds, int(count)).model_dump())


@router.put("/{ds_id}", response_model=ApiResponse)
async def update_datasource(
    ds_id: uuid.UUID,
    data: DatasourceUpdate,
    db: AsyncSession = Depends(get_db)
):
    """更新数据源(密码留空表示不修改)"""
    ds = await _get_ds(db, ds_id)
    update_data = data.model_dump(exclude_unset=True)

    if "db_type" in update_data:
        update_data["db_type"] = _validate_type(update_data["db_type"])
    effective_type = update_data.get("db_type", ds.db_type)
    schema = _validate_schema(effective_type, update_data.get("db_schema", ds.db_schema))
    if normalize_db_type(effective_type) == "dm":
        update_data["db_schema"] = schema
        update_data["database_name"] = ""
    if "password" in update_data:
        password = update_data.pop("password")
        if password:
            ds.password_enc = encrypt_password(password)
    if "name" in update_data and update_data["name"] != ds.name:
        exists = await db.execute(
            select(Datasource.id).where(
                Datasource.name == update_data["name"], Datasource.id != ds_id
            )
        )
        if exists.scalar_one_or_none():
            raise AlreadyExistsException("数据源名称已存在")

    for key, value in update_data.items():
        setattr(ds, key, value)

    await db.flush()
    await db.refresh(ds)
    # 配置变化后连接池必须重建
    dispose_engine(ds)
    return ApiResponse(data=_to_response(ds).model_dump(), message="更新成功")


@router.delete("/{ds_id}", response_model=ApiResponse)
async def delete_datasource(ds_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """删除数据源(同时清理连接缓存与向量索引)"""
    ds = await _get_ds(db, ds_id)
    await db.delete(ds)
    dispose_engine(ds)
    try:
        await rag_service.delete_datasource_vectors(str(ds_id))
    except Exception:
        pass
    return ApiResponse(message="删除成功")


@router.post("/{ds_id}/test-connection", response_model=ApiResponse)
async def test_connection(ds_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """测试已保存数据源的连接(真实建连并读取版本)"""
    ds = await _get_ds(db, ds_id)
    try:
        result = await engine_test_connection(ds)
    except Exception as e:
        ds.status = "error"
        await db.commit()
        return ApiResponse(code=1, message=str(e), data={"success": False, "message": str(e)})
    ds.status = "active"
    await db.flush()
    return ApiResponse(data=result, message=result["message"])


# ========== Schema / 线上表结构 / 预览 ==========

@router.get("/{ds_id}/schemas", response_model=ApiResponse)
async def list_schemas(ds_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """列出数据源可选的 schema/库名"""
    ds = await _get_ds(db, ds_id)
    try:
        return ApiResponse(data=await engine_list_schemas(ds))
    except Exception as e:
        raise DatasourceConnectionError(f"获取 Schema 失败: {e}")


@router.get("/{ds_id}/live-tables", response_model=ApiResponse)
async def list_live_tables(ds_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """实时读取数据源中的表清单(不落库)"""
    ds = await _get_ds(db, ds_id)
    try:
        return ApiResponse(data=await engine_list_tables(ds))
    except Exception as e:
        raise DatasourceConnectionError(f"读取表清单失败: {e}")


@router.get("/{ds_id}/live-tables/{table_name}/columns", response_model=ApiResponse)
async def list_live_columns(
    ds_id: uuid.UUID,
    table_name: str,
    db: AsyncSession = Depends(get_db)
):
    """实时读取单表字段(不落库)"""
    ds = await _get_ds(db, ds_id)
    try:
        return ApiResponse(data=await engine_list_columns(ds, table_name))
    except Exception as e:
        raise DatasourceConnectionError(f"读取字段失败: {e}")


@router.get("/{ds_id}/tables/{table_name}/preview", response_model=ApiResponse)
async def preview_table(
    ds_id: uuid.UUID,
    table_name: str,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db)
):
    """预览表数据"""
    ds = await _get_ds(db, ds_id)
    try:
        return ApiResponse(data=await engine_preview_table(ds, table_name, limit))
    except Exception as e:
        raise DatasourceConnectionError(f"预览数据失败: {e}")


# ========== 元数据(落库) ==========

@router.get("/{ds_id}/tables", response_model=ApiResponse)
async def list_tables(ds_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """获取已同步的表元数据列表"""
    await _get_ds(db, ds_id)
    result = await db.execute(
        select(TableMetadata)
        .where(TableMetadata.datasource_id == ds_id)
        .order_by(TableMetadata.table_name)
    )
    tables = result.scalars().all()
    items = [TableMetadataResponse.model_validate(t).model_dump() for t in tables]
    return ApiResponse(data=items)


@router.get("/{ds_id}/tables/{table_name}/columns", response_model=ApiResponse)
async def list_columns(
    ds_id: uuid.UUID,
    table_name: str,
    db: AsyncSession = Depends(get_db)
):
    """获取已同步的字段元数据"""
    result = await db.execute(
        select(TableMetadata).where(
            TableMetadata.datasource_id == ds_id,
            TableMetadata.table_name == table_name
        )
    )
    table = result.scalar_one_or_none()
    if not table:
        raise NotFoundException(f"表 {table_name} 不存在")

    result = await db.execute(
        select(ColumnMetadata)
        .where(ColumnMetadata.table_id == table.id)
        .order_by(ColumnMetadata.column_name)
    )
    columns = result.scalars().all()
    items = [ColumnMetadataResponse.model_validate(c).model_dump() for c in columns]
    return ApiResponse(data=items)


@router.post("/{ds_id}/upload-schema", response_model=ApiResponse)
async def upload_table_schema(
    ds_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """
    上传表结构文件，支持 DDL SQL 和 CSV 两种格式。
    DDL: CREATE TABLE 语句
    CSV: 表名,字段名,字段类型,字段注释,是否可空,是否主键
    """
    ds = await _get_ds(db, ds_id)

    content = await file.read()
    text = content.decode("utf-8-sig")
    filename = file.filename or ""

    imported_tables = []

    if filename.endswith(".csv"):
        imported_tables = await _parse_csv_schema(text, ds.id, db)
    elif filename.endswith(".sql") or filename.endswith(".ddl"):
        imported_tables = await _parse_ddl_schema(text, ds.id, db)
    else:
        # Try to auto-detect
        if text.strip().upper().startswith("CREATE"):
            imported_tables = await _parse_ddl_schema(text, ds.id, db)
        else:
            imported_tables = await _parse_csv_schema(text, ds.id, db)

    await db.flush()
    return ApiResponse(
        data={"imported_tables": len(imported_tables), "tables": imported_tables},
        message=f"成功导入 {len(imported_tables)} 张表"
    )


async def _parse_csv_schema(text: str, ds_id: uuid.UUID, db: AsyncSession) -> list:
    """Parse CSV format: table_name, column_name, column_type, comment, nullable, is_pk"""
    reader = csv.reader(io.StringIO(text))
    tables_data: dict = {}  # table_name -> [columns]

    for row in reader:
        if len(row) < 3:
            continue
        # Skip header
        if row[0].strip().lower() in ("table_name", "表名", "tablename"):
            continue

        table_name = row[0].strip()
        col_name = row[1].strip()
        col_type = row[2].strip()
        col_comment = row[3].strip() if len(row) > 3 else None
        nullable = int(row[4].strip()) if len(row) > 4 and row[4].strip() in ("0", "1", "true", "false", "yes", "no") else 1
        is_pk = int(row[5].strip()) if len(row) > 5 and row[5].strip() in ("0", "1", "true", "false", "yes", "no") else 0

        if table_name not in tables_data:
            tables_data[table_name] = []
        tables_data[table_name].append({
            "column_name": col_name,
            "column_type": col_type,
            "column_comment": col_comment,
            "is_nullable": nullable,
            "is_primary_key": is_pk,
        })

    return await _save_tables_to_db(tables_data, ds_id, db)


async def _parse_ddl_schema(text: str, ds_id: uuid.UUID, db: AsyncSession) -> list:
    """Parse DDL CREATE TABLE statements."""
    tables_data: dict = {}

    # Match CREATE TABLE blocks
    pattern = r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`"]?(\w+)[`"]?\s*\((.*?)\)'
    matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)

    for table_name, body in matches:
        columns = []
        # Parse each column line
        for line in body.split("\n"):
            line = line.strip().rstrip(",")
            if not line:
                continue
            # Skip constraints
            if line.upper().startswith(("PRIMARY KEY", "UNIQUE", "INDEX", "KEY", "CONSTRAINT", "FOREIGN")):
                continue

            # Parse column: name type [NOT NULL] [PRIMARY KEY] [COMMENT '...']
            col_match = re.match(
                r'[`"]?(\w+)[`"]?\s+(\w+(?:\([^)]*\))?)\s*(.*?)(?:,\s*)?$',
                line, re.IGNORECASE
            )
            if col_match:
                col_name = col_match.group(1)
                col_type = col_match.group(2)
                rest = col_match.group(3).upper()

                nullable = 0 if "NOT NULL" in rest else 1
                is_pk = 1 if "PRIMARY KEY" in rest else 0

                # Extract comment
                comment_match = re.search(r"COMMENT\s+['\"]([^'\"]+)['\"]", line, re.IGNORECASE)
                col_comment = comment_match.group(1) if comment_match else None

                columns.append({
                    "column_name": col_name,
                    "column_type": col_type,
                    "column_comment": col_comment,
                    "is_nullable": nullable,
                    "is_primary_key": is_pk,
                })

        if columns:
            tables_data[table_name] = columns

    return await _save_tables_to_db(tables_data, ds_id, db)


async def _save_tables_to_db(
    tables_data: dict,
    ds_id: uuid.UUID,
    db: AsyncSession,
    table_comments: Optional[dict] = None,
) -> list:
    """Save parsed table/column metadata to database, replacing existing."""
    imported = []
    comments = table_comments or {}
    for table_name, columns in tables_data.items():
        # Remove existing table metadata for this datasource+table
        result = await db.execute(
            select(TableMetadata).where(
                TableMetadata.datasource_id == ds_id,
                TableMetadata.table_name == table_name
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            # Delete old columns
            await db.execute(
                sql_delete(ColumnMetadata).where(ColumnMetadata.table_id == existing.id)
            )
            table_meta = existing
            if comments.get(table_name) is not None:
                table_meta.table_comment = comments.get(table_name)
        else:
            table_meta = TableMetadata(
                datasource_id=ds_id,
                table_name=table_name,
                table_comment=comments.get(table_name),
            )
            db.add(table_meta)
            await db.flush()

        # Add columns
        for col_data in columns:
            col = ColumnMetadata(
                table_id=table_meta.id,
                **col_data
            )
            db.add(col)

        imported.append({"table_name": table_name, "column_count": len(columns)})

    return imported


@router.post("/{ds_id}/sync-schema", response_model=ApiResponse)
async def sync_schema_from_db(
    ds_id: uuid.UUID,
    tables: Optional[str] = Query(None, description="仅同步指定表, 逗号分隔; 为空表示全部"),
    db: AsyncSession = Depends(get_db)
):
    """从数据源数据库自动同步表结构元数据(可指定表)"""
    ds = await _get_ds(db, ds_id)
    only_tables = [t.strip() for t in (tables or "").split(",") if t.strip()] or None
    try:
        result = await _sync_metadata(db, ds, only_tables)
        return ApiResponse(
            data=result,
            message=f"同步完成，共 {result['synced_tables']} 张表"
        )
    except Exception as e:
        ds.status = "error"
        await db.commit()
        raise DatasourceConnectionError(f"同步失败: {e}")
