import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from typing import List, Optional

from app.database import get_db
from app.models.student import Lead
from app.schemas.lead import LeadCreate, LeadUpdate, LeadOut
from app.dependencies import get_current_user, require_admin_or_teacher, require_permission

router = APIRouter(prefix="/leads", tags=["leads"])


@router.get("", response_model=List[LeadOut])
async def list_leads(
    stage: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    skip: int = 0,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("crm", "view")),
):
    q = select(Lead)
    if stage:
        q = q.where(Lead.stage == stage)
    if search:
        q = q.where(or_(
            Lead.full_name.ilike(f"%{search}%"),
            Lead.phone.ilike(f"%{search}%"),
        ))
    q = q.order_by(Lead.created_date.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("", response_model=LeadOut, status_code=201)
async def create_lead(data: LeadCreate, db: AsyncSession = Depends(get_db), _=Depends(require_admin_or_teacher)):
    lead = Lead(**data.model_dump())
    db.add(lead)
    await db.commit()
    await db.refresh(lead)
    return lead


@router.get("/{lead_id}", response_model=LeadOut)
async def get_lead(lead_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(404, "Lead not found")
    return lead


@router.patch("/{lead_id}", response_model=LeadOut)
async def update_lead(lead_id: uuid.UUID, data: LeadUpdate, db: AsyncSession = Depends(get_db), _=Depends(require_admin_or_teacher)):
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(404, "Lead not found")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(lead, k, v)
    await db.commit()
    await db.refresh(lead)
    return lead


@router.delete("/{lead_id}", status_code=204)
async def delete_lead(lead_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(require_admin_or_teacher)):
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(404, "Lead not found")
    await db.delete(lead)
    await db.commit()
