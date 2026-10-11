"""Semantic layer API: 语义模型/指标/维度管理。"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.semantic import SemanticModel, Metric, Dimension
from app.models.user import User
from app.schemas.schemas import (
    SemanticModelCreate, SemanticModelResponse,
    MetricCreate, MetricResponse,
    DimensionCreate, DimensionResponse,
    ApiResponse,
)
from app.core.deps import get_current_user
from app.core.exceptions import NotFoundException

router = APIRouter(prefix="/semantic", tags=["语义层"])


# ========== 语义模型 ==========

@router.get("/models", response_model=ApiResponse)
async def list_models(
    datasource_id: Optional[uuid.UUID] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """语义模型列表"""
    query = select(SemanticModel).options(selectinload(SemanticModel.metrics), selectinload(SemanticModel.dimensions))
    if datasource_id:
        query = query.where(SemanticModel.datasource_id == datasource_id)
    models = (await db.execute(query.order_by(SemanticModel.created_at.desc()))).scalars().all()
    items = []
    for m in models:
        items.append({
            **SemanticModelResponse.model_validate(m).model_dump(mode="json"),
            "metric_count": len(m.metrics),
            "dimension_count": len(m.dimensions),
        })
    return ApiResponse(data=items)


@router.post("/models", response_model=ApiResponse)
async def create_model(
    data: SemanticModelCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建语义模型"""
    model = SemanticModel(
        name=data.name, display_name=data.display_name,
        description=data.description, datasource_id=data.datasource_id,
        base_table=data.base_table, created_by=user.id,
    )
    db.add(model)
    await db.flush()
    await db.refresh(model)
    return ApiResponse(data=SemanticModelResponse.model_validate(model).model_dump(mode="json"))


@router.get("/models/{model_id}", response_model=ApiResponse)
async def get_model(
    model_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """模型详情(含指标/维度)"""
    model = (await db.execute(
        select(SemanticModel)
        .options(selectinload(SemanticModel.metrics), selectinload(SemanticModel.dimensions))
        .where(SemanticModel.id == model_id)
    )).scalar_one_or_none()
    if not model:
        raise NotFoundException("语义模型不存在")
    data = SemanticModelResponse.model_validate(model).model_dump(mode="json")
    data["metrics"] = [MetricResponse.model_validate(m).model_dump(mode="json") for m in model.metrics]
    data["dimensions"] = [DimensionResponse.model_validate(d).model_dump(mode="json") for d in model.dimensions]
    return ApiResponse(data=data)


@router.put("/models/{model_id}", response_model=ApiResponse)
async def update_model(
    model_id: uuid.UUID,
    data: SemanticModelCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新语义模型"""
    model = (await db.execute(select(SemanticModel).where(SemanticModel.id == model_id))).scalar_one_or_none()
    if not model:
        raise NotFoundException("语义模型不存在")
    model.name = data.name
    model.display_name = data.display_name
    model.description = data.description
    model.datasource_id = data.datasource_id
    model.base_table = data.base_table
    await db.flush()
    await db.refresh(model)
    return ApiResponse(data=SemanticModelResponse.model_validate(model).model_dump(mode="json"))


@router.delete("/models/{model_id}", response_model=ApiResponse)
async def delete_model(
    model_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除语义模型(级联删除指标/维度)"""
    model = (await db.execute(select(SemanticModel).where(SemanticModel.id == model_id))).scalar_one_or_none()
    if not model:
        raise NotFoundException("语义模型不存在")
    await db.delete(model)
    return ApiResponse(message="删除成功")


# ========== 指标 ==========

@router.post("/models/{model_id}/metrics", response_model=ApiResponse)
async def create_metric(
    model_id: uuid.UUID,
    data: MetricCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建指标"""
    model = (await db.execute(select(SemanticModel).where(SemanticModel.id == model_id))).scalar_one_or_none()
    if not model:
        raise NotFoundException("语义模型不存在")
    metric = Metric(
        model_id=model_id, name=data.name, display_name=data.display_name,
        description=data.description, expression=data.expression,
        data_type=data.data_type, dimensions=data.dimensions,
        synonyms=data.synonyms, tags=data.tags,
    )
    db.add(metric)
    await db.flush()
    await db.refresh(metric)
    return ApiResponse(data=MetricResponse.model_validate(metric).model_dump(mode="json"))


@router.put("/models/{model_id}/metrics/{metric_id}", response_model=ApiResponse)
async def update_metric(
    model_id: uuid.UUID,
    metric_id: uuid.UUID,
    data: MetricCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新指标"""
    metric = (await db.execute(select(Metric).where(
        Metric.id == metric_id, Metric.model_id == model_id))).scalar_one_or_none()
    if not metric:
        raise NotFoundException("指标不存在")
    metric.name = data.name
    metric.display_name = data.display_name
    metric.description = data.description
    metric.expression = data.expression
    metric.data_type = data.data_type
    metric.dimensions = data.dimensions
    metric.synonyms = data.synonyms
    metric.tags = data.tags
    await db.flush()
    await db.refresh(metric)
    return ApiResponse(data=MetricResponse.model_validate(metric).model_dump(mode="json"))


@router.delete("/models/{model_id}/metrics/{metric_id}", response_model=ApiResponse)
async def delete_metric(
    model_id: uuid.UUID,
    metric_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除指标"""
    metric = (await db.execute(select(Metric).where(
        Metric.id == metric_id, Metric.model_id == model_id))).scalar_one_or_none()
    if not metric:
        raise NotFoundException("指标不存在")
    await db.delete(metric)
    return ApiResponse(message="删除成功")


# ========== 维度 ==========

@router.post("/models/{model_id}/dimensions", response_model=ApiResponse)
async def create_dimension(
    model_id: uuid.UUID,
    data: DimensionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建维度"""
    model = (await db.execute(select(SemanticModel).where(SemanticModel.id == model_id))).scalar_one_or_none()
    if not model:
        raise NotFoundException("语义模型不存在")
    dim = Dimension(
        model_id=model_id, name=data.name, display_name=data.display_name,
        description=data.description, column_name=data.column_name,
        data_type=data.data_type, hierarchy_level=data.hierarchy_level,
        synonyms=data.synonyms,
    )
    db.add(dim)
    await db.flush()
    await db.refresh(dim)
    return ApiResponse(data=DimensionResponse.model_validate(dim).model_dump(mode="json"))


@router.put("/models/{model_id}/dimensions/{dim_id}", response_model=ApiResponse)
async def update_dimension(
    model_id: uuid.UUID,
    dim_id: uuid.UUID,
    data: DimensionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新维度"""
    dim = (await db.execute(select(Dimension).where(
        Dimension.id == dim_id, Dimension.model_id == model_id))).scalar_one_or_none()
    if not dim:
        raise NotFoundException("维度不存在")
    dim.name = data.name
    dim.display_name = data.display_name
    dim.description = data.description
    dim.column_name = data.column_name
    dim.data_type = data.data_type
    dim.hierarchy_level = data.hierarchy_level
    dim.synonyms = data.synonyms
    await db.flush()
    await db.refresh(dim)
    return ApiResponse(data=DimensionResponse.model_validate(dim).model_dump(mode="json"))


@router.delete("/models/{model_id}/dimensions/{dim_id}", response_model=ApiResponse)
async def delete_dimension(
    model_id: uuid.UUID,
    dim_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除维度"""
    dim = (await db.execute(select(Dimension).where(
        Dimension.id == dim_id, Dimension.model_id == model_id))).scalar_one_or_none()
    if not dim:
        raise NotFoundException("维度不存在")
    await db.delete(dim)
    return ApiResponse(message="删除成功")
