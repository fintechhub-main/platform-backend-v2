from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List, Optional
import uuid

from app.database import get_db
from app.models.fine import Fine
from app.models.user import User, UserRole
from app.models.group import Group, GroupStudent
from app.schemas.fine import FineCreate, FineUpdate, FineOut
from app.dependencies import require_permission

router = APIRouter(prefix="/fines", tags=["fines"])


@router.get("", response_model=List[FineOut])
async def list_fines(
    role: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    branch_id: Optional[str] = Query(None),
    skip: int = 0, limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("fines", "view")),
):
    q = select(Fine).options(selectinload(Fine.user))
    if role:
        q = q.join(User).where(User.role == role)
    if search:
        q = q.join(User, isouter=True).where(User.full_name.ilike(f"%{search}%"))
    if branch_id:
        branch_uuid = uuid.UUID(branch_id)
        user_ids_in_branch = (
            select(GroupStudent.student_id)
            .join(Group)
            .where(Group.branch_id == branch_uuid)
            .distinct()
        )
        q = q.where(Fine.user_id.in_(user_ids_in_branch))
    result = await db.execute(q.offset(skip).limit(limit).order_by(Fine.date.desc()))
    return result.scalars().all()


@router.post("", response_model=FineOut, status_code=201)
async def create_fine(data: FineCreate, db: AsyncSession = Depends(get_db), _=Depends(require_permission("fines", "create"))):
    fine = Fine(**data.model_dump())
    db.add(fine)
    await db.commit()
    await db.refresh(fine)
    result = await db.execute(select(Fine).options(selectinload(Fine.user)).where(Fine.id == fine.id))
    return result.scalar_one()


@router.patch("/{fine_id}", response_model=FineOut)
async def update_fine(fine_id: uuid.UUID, data: FineUpdate, db: AsyncSession = Depends(get_db), _=Depends(require_permission("fines", "update"))):
    result = await db.execute(select(Fine).where(Fine.id == fine_id))
    fine = result.scalar_one_or_none()
    if not fine:
        raise HTTPException(404, "Fine not found")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(fine, k, v)
    await db.commit()
    await db.refresh(fine)
    return fine


@router.delete("/{fine_id}", status_code=204)
async def delete_fine(fine_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(require_permission("fines", "delete"))):
    result = await db.execute(select(Fine).where(Fine.id == fine_id))
    fine = result.scalar_one_or_none()
    if not fine:
        raise HTTPException(404, "Fine not found")
    await db.delete(fine)
    await db.commit()
