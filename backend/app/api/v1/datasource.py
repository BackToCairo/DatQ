"""Datasource API routes."""
import uuid
import csv
import io
import re
from typing import List
from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete as sql_delete
from app.database import get_db
from app.models.datasource import Datasource, TableMetadata, ColumnMetadata
from app.schemas.schemas import (
    DatasourceCreate, DatasourceResponse, DatasourceUpdate,
    TableMetadataResponse, ColumnMetadataResponse, ApiResponse
)
from app.core.exceptions import NotFoundException, DatasourceConnectionError
from app.services.auth_service import AuthService
from app.engines import encrypt_password, dispose_engine
from app.engines import test_connection as engine_test_connection
from app.services import rag_service

router = APIRouter(prefix="/datasources", tags=["数据源"])


@router.get("", response_model=ApiResponse)
async def list_datasources(
    authorization: str = None,
    db: AsyncSession = Depends(get_db)
):
    """获取数据源列表"""
    result = await db.execute(select(Datasource).order_by(Datasource.created_at.desc()))
    datasources = result.scalars().all()
    items = [DatasourceResponse.model_validate(ds).model_dump() for ds in datasources]
    return ApiResponse(data=items)


@router.post("", response_model=ApiResponse)
async def create_datasource(
    data: DatasourceCreate,
    authorization: str = None,
    db: AsyncSession = Depends(get_db)
):
    """创建数据源"""
    ds = Datasource(
        name=data.name,
        db_type=data.db_type,
        host=data.host,
        port=data.port,
        database_name=data.database_name,
        username=data.username,
        password_enc=encrypt_password(data.password),  # Fernet 加密存储
        pool_size=data.pool_size,
        pool_timeout=data.pool_timeout,
        extra_params=data.extra_params,
    )
    db.add(ds)
    await db.flush()
    await db.refresh(ds)
    return ApiResponse(data=DatasourceResponse.model_validate(ds).model_dump())


@router.get("/{ds_id}", response_model=ApiResponse)
async def get_datasource(ds_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """获取数据源详情"""
    result = await db.execute(select(Datasource).where(Datasource.id == ds_id))
    ds = result.scalar_one_or_none()
    if not ds:
        raise NotFoundException("数据源不存在")
    return ApiResponse(data=DatasourceResponse.model_validate(ds).model_dump())


@router.put("/{ds_id}", response_model=ApiResponse)
async def update_datasource(
    ds_id: uuid.UUID,
    data: DatasourceUpdate,
    db: AsyncSession = Depends(get_db)
):
    """更新数据源"""
    result = await db.execute(select(Datasource).where(Datasource.id == ds_id))
    ds = result.scalar_one_or_none()
    if not ds:
        raise NotFoundException("数据源不存在")

    update_data = data.model_dump(exclude_unset=True)
    if "password" in update_data:
        ds.password_enc = update_data.pop("password").encode()
    for key, value in update_data.items():
        setattr(ds, key, value)

    await db.flush()
    await db.refresh(ds)
    return ApiResponse(data=DatasourceResponse.model_validate(ds).model_dump())


@router.delete("/{ds_id}", response_model=ApiResponse)
async def delete_datasource(ds_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """删除数据源(同时清理连接缓存与向量索引)"""
    result = await db.execute(select(Datasource).where(Datasource.id == ds_id))
    ds = result.scalar_one_or_none()
    if not ds:
        raise NotFoundException("数据源不存在")
    await db.delete(ds)
    dispose_engine(ds)
    try:
        await rag_service.delete_datasource_vectors(str(ds_id))
    except Exception:
        pass
    return ApiResponse(message="删除成功")


@router.post("/{ds_id}/test-connection", response_model=ApiResponse)
async def test_connection(ds_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """测试数据源连接(真实建连并执行SELECT 1)"""
    result = await db.execute(select(Datasource).where(Datasource.id == ds_id))
    ds = result.scalar_one_or_none()
    if not ds:
        raise NotFoundException("数据源不存在")

    try:
        data = await engine_test_connection(ds)
        ds.status = "active"
        return ApiResponse(data=data, message="连接成功")
    except Exception as e:
        ds.status = "error"
        raise DatasourceConnectionError(f"连接失败: {str(e)}")


@router.get("/{ds_id}/tables", response_model=ApiResponse)
async def list_tables(ds_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """获取数据源的表列表"""
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
    """获取表的字段列表"""
    # Find table
    result = await db.execute(
        select(TableMetadata).where(
            TableMetadata.datasource_id == ds_id,
            TableMetadata.table_name == table_name
        )
    )
    table = result.scalar_one_or_none()
    if not table:
        raise NotFoundException(f"表 {table_name} 不存在")

    # Get columns
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
    result = await db.execute(select(Datasource).where(Datasource.id == ds_id))
    ds = result.scalar_one_or_none()
    if not ds:
        raise NotFoundException("数据源不存在")

    content = await file.read()
    text = content.decode("utf-8-sig")
    filename = file.filename or ""

    imported_tables = []

    if filename.endswith(".csv"):
        imported_tables = await _parse_csv_schema(text, ds_id, db)
    elif filename.endswith(".sql") or filename.endswith(".ddl"):
        imported_tables = await _parse_ddl_schema(text, ds_id, db)
    else:
        # Try to auto-detect
        if text.strip().upper().startswith("CREATE"):
            imported_tables = await _parse_ddl_schema(text, ds_id, db)
        else:
            imported_tables = await _parse_csv_schema(text, ds_id, db)

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


async def _save_tables_to_db(tables_data: dict, ds_id: uuid.UUID, db: AsyncSession) -> list:
    """Save parsed table/column metadata to database, replacing existing."""
    imported = []
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
        else:
            table_meta = TableMetadata(
                datasource_id=ds_id,
                table_name=table_name,
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
    db: AsyncSession = Depends(get_db)
):
    """从数据源数据库自动同步表结构元数据"""
    result = await db.execute(select(Datasource).where(Datasource.id == ds_id))
    ds = result.scalar_one_or_none()
    if not ds:
        raise NotFoundException("数据源不存在")

    try:
        from app.engines import sync_schema
        tables_info = await sync_schema(ds)
        # Save to metadata tables
        tables_data = {}
        for t in tables_info:
            tables_data[t["table_name"]] = t["columns"]
        imported = await _save_tables_to_db(tables_data, ds_id, db)
        ds.last_sync_at = __import__("datetime").datetime.utcnow()
        ds.status = "active"
        await db.flush()

        # DDL 同步入向量库, 用于 NL2SQL Schema Linking
        try:
            await rag_service.index_ddl(str(ds_id), tables_info)
        except Exception:
            pass

        return ApiResponse(
            data={"synced_tables": len(imported), "tables": imported},
            message=f"同步完成，共 {len(imported)} 张表"
        )
    except ImportError:
        raise DatasourceConnectionError("数据库引擎未配置")
    except Exception as e:
        ds.status = "error"
        raise DatasourceConnectionError(f"同步失败: {str(e)}")
