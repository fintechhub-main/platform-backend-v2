import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import Optional, List

from app.database import get_db
from app.models.branch import Branch
from app.models.group import Group
from app.dependencies import get_current_user

router = APIRouter(prefix="/branches", tags=["branches"])


class BranchCreate(BaseModel):
    name: str
    address: Optional[str] = None
    color: Optional[str] = None


class BranchOut(BaseModel):
    id: uuid.UUID
    name: str
    address: Optional[str] = None
    color: Optional[str] = None
    is_active: bool

    model_config = {"from_attributes": True}


@router.get("", response_model=list[BranchOut])
async def list_branches(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    rows = (await db.execute(select(Branch).where(Branch.is_active == True).order_by(Branch.name))).scalars().all()
    return rows


@router.post("", response_model=BranchOut)
async def create_branch(data: BranchCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    branch = Branch(**data.model_dump())
    db.add(branch)
    await db.commit()
    await db.refresh(branch)
    return branch


@router.put("/{branch_id}", response_model=BranchOut)
async def update_branch(branch_id: uuid.UUID, data: BranchCreate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    branch = (await db.execute(select(Branch).where(Branch.id == branch_id))).scalar_one_or_none()
    if not branch:
        raise HTTPException(404, "Branch not found")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(branch, k, v)
    await db.commit()
    await db.refresh(branch)
    return branch


@router.delete("/{branch_id}")
async def delete_branch(branch_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    branch = (await db.execute(select(Branch).where(Branch.id == branch_id))).scalar_one_or_none()
    if not branch:
        raise HTTPException(404, "Branch not found")
    branch.is_active = False
    await db.commit()
    return {"ok": True}


class BulkAssignBody(BaseModel):
    group_ids: List[uuid.UUID]


@router.post("/{branch_id}/assign-groups")
async def assign_groups(
    branch_id: uuid.UUID,
    body: BulkAssignBody,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    await db.execute(
        update(Group)
        .where(Group.id.in_(body.group_ids))
        .values(branch_id=branch_id)
    )
    await db.commit()
    return {"assigned": len(body.group_ids)}


@router.post("/{branch_id}/assign-all-groups")
async def assign_all_groups(
    branch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Assign all groups that have no branch to this branch."""
    result = await db.execute(
        update(Group)
        .where(Group.branch_id == None)
        .values(branch_id=branch_id)
        .returning(Group.id)
    )
    await db.commit()
    return {"assigned": len(result.all())}


@router.get("/{branch_id}/groups")
async def get_branch_groups(
    branch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    rows = (await db.execute(
        select(Group.id, Group.name, Group.status)
        .where(Group.branch_id == branch_id)
        .order_by(Group.name)
    )).all()
    return [{"id": str(r.id), "name": r.name, "status": r.status} for r in rows]
