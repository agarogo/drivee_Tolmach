from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin
from app.models import User
from app.schemas import ApprovedTemplateCreate, ApprovedTemplateOut, ApprovedTemplatePatch, DimensionCatalogCreate, DimensionCatalogOut, DimensionCatalogPatch, MetricCatalogCreate, MetricCatalogOut, MetricCatalogPatch, SemanticExampleCreate, SemanticExampleOut, SemanticExamplePatch, SemanticTermCreate, SemanticTermOut, SemanticTermPatch, SemanticValidationReportOut
from app.semantic import repository as semantic_repository
from app.semantic.service import create_approved_template_entry, create_dimension_catalog_entry, create_metric_catalog_entry, create_semantic_example_entry, create_semantic_term_entry, delete_approved_template_entry, delete_dimension_catalog_entry, delete_metric_catalog_entry, delete_semantic_example_entry, delete_semantic_term_entry, update_approved_template_entry, update_dimension_catalog_entry, update_metric_catalog_entry, update_semantic_example_entry, update_semantic_term_entry, validate_semantic_layer


router = APIRouter(prefix="/admin/semantic", tags=["Admin semantic"])


@router.get("/validate", response_model=SemanticValidationReportOut)
async def admin_validate_semantic_catalog(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> SemanticValidationReportOut:
    return SemanticValidationReportOut.model_validate((await validate_semantic_layer(db)).as_dict())


@router.get("/metrics", response_model=list[MetricCatalogOut])
async def admin_list_metric_catalog(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[MetricCatalogOut]:
    rows = await semantic_repository.list_metric_catalog_entries(db)
    return [MetricCatalogOut.model_validate(row) for row in rows]


@router.post("/metrics", response_model=MetricCatalogOut)
async def admin_create_metric_catalog(
    payload: MetricCatalogCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> MetricCatalogOut:
    item = await create_metric_catalog_entry(db, payload.model_dump(), updated_by=user.id)
    return MetricCatalogOut.model_validate(item)


@router.patch("/metrics/{metric_key}", response_model=MetricCatalogOut)
async def admin_update_metric_catalog(
    metric_key: str,
    payload: MetricCatalogPatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> MetricCatalogOut:
    item = await update_metric_catalog_entry(
        db,
        metric_key,
        payload.model_dump(exclude_unset=True),
        updated_by=user.id,
    )
    return MetricCatalogOut.model_validate(item)


@router.delete("/metrics/{metric_key}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_metric_catalog(
    metric_key: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> None:
    await delete_metric_catalog_entry(db, metric_key)


@router.get("/dimensions", response_model=list[DimensionCatalogOut])
async def admin_list_dimension_catalog(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[DimensionCatalogOut]:
    rows = await semantic_repository.list_dimension_catalog_entries(db)
    return [DimensionCatalogOut.model_validate(row) for row in rows]


@router.post("/dimensions", response_model=DimensionCatalogOut)
async def admin_create_dimension_catalog(
    payload: DimensionCatalogCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> DimensionCatalogOut:
    item = await create_dimension_catalog_entry(db, payload.model_dump(), updated_by=user.id)
    return DimensionCatalogOut.model_validate(item)


@router.patch("/dimensions/{dimension_key}", response_model=DimensionCatalogOut)
async def admin_update_dimension_catalog(
    dimension_key: str,
    payload: DimensionCatalogPatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> DimensionCatalogOut:
    item = await update_dimension_catalog_entry(
        db,
        dimension_key,
        payload.model_dump(exclude_unset=True),
        updated_by=user.id,
    )
    return DimensionCatalogOut.model_validate(item)


@router.delete("/dimensions/{dimension_key}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_dimension_catalog(
    dimension_key: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> None:
    await delete_dimension_catalog_entry(db, dimension_key)


@router.get("/terms", response_model=list[SemanticTermOut])
async def admin_list_semantic_terms(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[SemanticTermOut]:
    rows = await semantic_repository.list_semantic_terms(db)
    return [SemanticTermOut.model_validate(row) for row in rows]


@router.post("/terms", response_model=SemanticTermOut)
async def admin_create_semantic_term(
    payload: SemanticTermCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> SemanticTermOut:
    item = await create_semantic_term_entry(db, payload.model_dump(), updated_by=user.id)
    return SemanticTermOut.model_validate(item)


@router.patch("/terms/{term}", response_model=SemanticTermOut)
async def admin_update_semantic_term(
    term: str,
    payload: SemanticTermPatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> SemanticTermOut:
    item = await update_semantic_term_entry(db, term, payload.model_dump(exclude_unset=True), updated_by=user.id)
    return SemanticTermOut.model_validate(item)


@router.delete("/terms/{term}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_semantic_term(
    term: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> None:
    await delete_semantic_term_entry(db, term)


@router.get("/examples", response_model=list[SemanticExampleOut])
async def admin_list_semantic_examples(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[SemanticExampleOut]:
    rows = await semantic_repository.list_semantic_examples(db)
    return [SemanticExampleOut.model_validate(row) for row in rows]


@router.post("/examples", response_model=SemanticExampleOut)
async def admin_create_semantic_example(
    payload: SemanticExampleCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> SemanticExampleOut:
    item = await create_semantic_example_entry(db, payload.model_dump(), updated_by=user.id)
    return SemanticExampleOut.model_validate(item)


@router.patch("/examples/{example_id}", response_model=SemanticExampleOut)
async def admin_update_semantic_example(
    example_id: UUID,
    payload: SemanticExamplePatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> SemanticExampleOut:
    item = await update_semantic_example_entry(
        db,
        example_id,
        payload.model_dump(exclude_unset=True),
        updated_by=user.id,
    )
    return SemanticExampleOut.model_validate(item)


@router.delete("/examples/{example_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_semantic_example(
    example_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> None:
    await delete_semantic_example_entry(db, example_id)


@router.get("/approved-templates", response_model=list[ApprovedTemplateOut])
async def admin_list_approved_templates(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[ApprovedTemplateOut]:
    rows = await semantic_repository.list_approved_templates(db)
    return [ApprovedTemplateOut.model_validate(row) for row in rows]


@router.post("/approved-templates", response_model=ApprovedTemplateOut)
async def admin_create_approved_template(
    payload: ApprovedTemplateCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> ApprovedTemplateOut:
    item = await create_approved_template_entry(db, payload.model_dump(), updated_by=user.id)
    return ApprovedTemplateOut.model_validate(item)


@router.patch("/approved-templates/{template_key}", response_model=ApprovedTemplateOut)
async def admin_update_approved_template(
    template_key: str,
    payload: ApprovedTemplatePatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> ApprovedTemplateOut:
    item = await update_approved_template_entry(
        db,
        template_key,
        payload.model_dump(exclude_unset=True),
        updated_by=user.id,
    )
    return ApprovedTemplateOut.model_validate(item)


@router.delete("/approved-templates/{template_key}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_approved_template(
    template_key: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> None:
    await delete_approved_template_entry(db, template_key)
