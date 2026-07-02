import uuid
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.database import get_db
from app.models.material import GroupMaterial
from app.models.user import User
from app.dependencies import get_current_user, require_permission

router = APIRouter(prefix="/groups", tags=["materials"])


class MaterialCreate(BaseModel):
    title: str
    file_url: Optional[str] = None
    description: Optional[str] = None


class MaterialOut(BaseModel):
    id: uuid.UUID
    group_id: uuid.UUID
    title: str
    file_url: Optional[str]
    description: Optional[str]
    added_by: Optional[uuid.UUID]
    added_by_name: Optional[str] = None
    added_at: datetime
    is_confirmed: bool

    model_config = {"from_attributes": True}


@router.get("/{group_id}/materials", response_model=List[MaterialOut])
async def list_materials(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("groups", "view")),
):
    rows = (await db.execute(
        select(GroupMaterial, User.full_name)
        .outerjoin(User, User.id == GroupMaterial.added_by)
        .where(GroupMaterial.group_id == group_id)
        .order_by(GroupMaterial.added_at.desc())
    )).all()
    result = []
    for mat, added_by_name in rows:
        out = MaterialOut.model_validate(mat)
        out.added_by_name = added_by_name
        result.append(out)
    return result


@router.post("/{group_id}/materials", response_model=MaterialOut, status_code=201)
async def create_material(
    group_id: uuid.UUID,
    data: MaterialCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("groups", "update")),
):
    mat = GroupMaterial(
        group_id=group_id,
        title=data.title,
        file_url=data.file_url,
        description=data.description,
        added_by=current_user.id,
        is_confirmed=True,
    )
    db.add(mat)
    await db.commit()
    await db.refresh(mat)
    out = MaterialOut.model_validate(mat)
    out.added_by_name = current_user.full_name
    return out


@router.patch("/{group_id}/materials/{material_id}", response_model=MaterialOut)
async def update_material(
    group_id: uuid.UUID,
    material_id: uuid.UUID,
    data: MaterialCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("groups", "update")),
):
    mat = (await db.execute(
        select(GroupMaterial)
        .where(GroupMaterial.id == material_id, GroupMaterial.group_id == group_id)
    )).scalar_one_or_none()
    if not mat:
        raise HTTPException(404, "Not found")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(mat, k, v)
    await db.commit()
    await db.refresh(mat)
    return MaterialOut.model_validate(mat)


@router.delete("/{group_id}/materials/{material_id}", status_code=204)
async def delete_material(
    group_id: uuid.UUID,
    material_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("groups", "delete")),
):
    mat = (await db.execute(
        select(GroupMaterial)
        .where(GroupMaterial.id == material_id, GroupMaterial.group_id == group_id)
    )).scalar_one_or_none()
    if not mat:
        raise HTTPException(404, "Not found")
    await db.delete(mat)
    await db.commit()
