from app.api.common import *


router = APIRouter(tags=["Templates"])


@router.get("/templates", response_model=list[TemplateOut])
@router.get("/api/templates", response_model=list[TemplateOut])
async def list_templates(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> list[TemplateOut]:
    rows = list(
        (
            await db.scalars(
                select(Template)
                .where(or_(Template.is_public.is_(True), Template.created_by == user.id))
                .order_by(Template.category.asc(), Template.use_count.desc(), Template.title.asc())
            )
        ).all()
    )
    return [TemplateOut.model_validate(row) for row in rows]


@router.post("/templates", response_model=TemplateOut)
@router.post("/api/templates", response_model=TemplateOut)
async def create_template(
    payload: TemplateCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TemplateOut:
    item = Template(created_by=user.id, **payload.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return TemplateOut.model_validate(item)
