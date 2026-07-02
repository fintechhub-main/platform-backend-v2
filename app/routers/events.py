import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from app.database import get_db
from app.models.event import Event, EventRegistration
from app.models.user import User, UserRole
from app.dependencies import get_current_user, require_permission

router = APIRouter(prefix="/events", tags=["events"])


class EventCreate(BaseModel):
    title: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    event_date: str
    event_time: Optional[str] = None
    location: Optional[str] = None
    branch_id: Optional[str] = None
    max_participants: Optional[int] = None
    is_active: bool = True


class EventUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    event_date: Optional[str] = None
    event_time: Optional[str] = None
    location: Optional[str] = None
    branch_id: Optional[str] = None
    max_participants: Optional[int] = None
    is_active: Optional[bool] = None


def _event_out(event: Event, reg_count: int = 0, is_registered: bool = False):
    return {
        "id": str(event.id),
        "title": event.title,
        "description": event.description,
        "image_url": event.image_url,
        "event_date": str(event.event_date),
        "event_time": event.event_time,
        "location": event.location,
        "branch_id": str(event.branch_id) if event.branch_id else None,
        "max_participants": event.max_participants,
        "is_active": event.is_active,
        "created_at": event.created_at.isoformat(),
        "registration_count": reg_count,
        "is_registered": is_registered,
    }


@router.get("")
async def list_events(
    branch_id: Optional[str] = Query(None),
    active_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("events", "view")),
):
    q = select(Event)
    if branch_id:
        q = q.where(Event.branch_id == uuid.UUID(branch_id))
    if active_only:
        q = q.where(Event.is_active == True)
    q = q.order_by(Event.event_date.desc())
    events = (await db.execute(q)).scalars().all()

    result = []
    for event in events:
        cnt = (await db.execute(
            select(func.count()).where(EventRegistration.event_id == event.id)
        )).scalar() or 0
        is_reg = False
        if current_user.role == UserRole.student:
            reg = (await db.execute(
                select(EventRegistration).where(
                    EventRegistration.event_id == event.id,
                    EventRegistration.student_id == current_user.id
                )
            )).scalar_one_or_none()
            is_reg = reg is not None
        result.append(_event_out(event, cnt, is_reg))
    return result


@router.post("", status_code=201)
async def create_event(data: EventCreate, db: AsyncSession = Depends(get_db), _=Depends(require_permission("events", "create"))):
    from datetime import date
    event = Event(
        title=data.title,
        description=data.description,
        image_url=data.image_url,
        event_date=date.fromisoformat(data.event_date),
        event_time=data.event_time,
        location=data.location,
        branch_id=uuid.UUID(data.branch_id) if data.branch_id else None,
        max_participants=data.max_participants,
        is_active=data.is_active,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return _event_out(event)


@router.patch("/{event_id}")
async def update_event(event_id: uuid.UUID, data: EventUpdate, db: AsyncSession = Depends(get_db), _=Depends(require_permission("events", "update"))):
    from datetime import date
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Event not found")
    for k, v in data.model_dump(exclude_none=True).items():
        if k == "event_date" and v:
            v = date.fromisoformat(v)
        if k == "branch_id" and v:
            v = uuid.UUID(v)
        setattr(event, k, v)
    await db.commit()
    await db.refresh(event)
    return _event_out(event)


@router.delete("/{event_id}", status_code=204)
async def delete_event(event_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(require_permission("events", "delete"))):
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Not found")
    await db.delete(event)
    await db.commit()


@router.get("/{event_id}/registrations")
async def list_registrations(event_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    rows = (await db.execute(
        select(EventRegistration, User.full_name, User.phone)
        .join(User, User.id == EventRegistration.student_id)
        .where(EventRegistration.event_id == event_id)
        .order_by(EventRegistration.registered_at)
    )).all()
    return [
        {
            "id": str(r.id),
            "student_id": str(r.student_id),
            "student_name": full_name,
            "student_phone": phone,
            "registered_at": r.registered_at.isoformat(),
        }
        for r, full_name, phone in rows
    ]


@router.post("/{event_id}/register", status_code=201)
async def register_for_event(event_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if not event or not event.is_active:
        raise HTTPException(404, "Tadbir topilmadi")

    existing = (await db.execute(
        select(EventRegistration).where(
            EventRegistration.event_id == event_id,
            EventRegistration.student_id == current_user.id
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(400, "Allaqachon ro'yxatga kirgansiz")

    if event.max_participants:
        cnt = (await db.execute(
            select(func.count()).where(EventRegistration.event_id == event_id)
        )).scalar() or 0
        if cnt >= event.max_participants:
            raise HTTPException(400, "Tadbir to'ldi")

    reg = EventRegistration(event_id=event_id, student_id=current_user.id)
    db.add(reg)
    await db.commit()
    return {"ok": True}


@router.delete("/{event_id}/register", status_code=204)
async def unregister_from_event(event_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    reg = (await db.execute(
        select(EventRegistration).where(
            EventRegistration.event_id == event_id,
            EventRegistration.student_id == current_user.id
        )
    )).scalar_one_or_none()
    if reg:
        await db.delete(reg)
        await db.commit()
