import uuid
from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from pydantic import BaseModel
from app.database import get_db
from app.models.holiday import Holiday
from app.dependencies import require_permission

router = APIRouter(prefix="/holidays", tags=["holidays"])


class HolidayCreate(BaseModel):
    name: str
    start_date: str
    end_date: str
    color: Optional[str] = "#f59e0b"
    branch_id: Optional[str] = None


class HolidayUpdate(BaseModel):
    name: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    color: Optional[str] = None
    branch_id: Optional[str] = None


def _out(h: Holiday):
    return {
        "id": str(h.id),
        "name": h.name,
        "start_date": str(h.start_date),
        "end_date": str(h.end_date),
        "color": h.color or "#f59e0b",
        "branch_id": str(h.branch_id) if h.branch_id else None,
        "created_at": h.created_at.isoformat(),
    }


@router.get("")
async def list_holidays(
    branch_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("settings", "view")),
):
    q = select(Holiday).order_by(Holiday.start_date)
    if branch_id:
        q = q.where(
            or_(Holiday.branch_id == uuid.UUID(branch_id), Holiday.branch_id.is_(None))
        )
    holidays = (await db.execute(q)).scalars().all()
    return [_out(h) for h in holidays]


@router.post("", status_code=201)
async def create_holiday(data: HolidayCreate, db: AsyncSession = Depends(get_db), _=Depends(require_permission("settings", "create"))):
    holiday = Holiday(
        name=data.name,
        start_date=date.fromisoformat(data.start_date),
        end_date=date.fromisoformat(data.end_date),
        color=data.color,
        branch_id=uuid.UUID(data.branch_id) if data.branch_id else None,
    )
    db.add(holiday)
    await db.commit()
    await db.refresh(holiday)
    return _out(holiday)


@router.patch("/{holiday_id}")
async def update_holiday(holiday_id: uuid.UUID, data: HolidayUpdate, db: AsyncSession = Depends(get_db), _=Depends(require_permission("settings", "update"))):
    h = (await db.execute(select(Holiday).where(Holiday.id == holiday_id))).scalar_one_or_none()
    if not h:
        raise HTTPException(404, "Not found")
    for k, v in data.model_dump(exclude_none=True).items():
        if k in ("start_date", "end_date") and v:
            v = date.fromisoformat(v)
        if k == "branch_id" and v:
            v = uuid.UUID(v)
        setattr(h, k, v)
    await db.commit()
    await db.refresh(h)
    return _out(h)


@router.delete("/{holiday_id}", status_code=204)
async def delete_holiday(holiday_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(require_permission("settings", "delete"))):
    h = (await db.execute(select(Holiday).where(Holiday.id == holiday_id))).scalar_one_or_none()
    if not h:
        raise HTTPException(404, "Not found")
    await db.delete(h)
    await db.commit()
