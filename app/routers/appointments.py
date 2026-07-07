import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import get_current_user
from app.models.appointment import TeacherAppointment
from app.models.user import User

router = APIRouter(prefix="/appointments", tags=["appointments"])


class AppointmentCreate(BaseModel):
    teacher_id: str
    date: str  # ISO format: "2025-07-15T10:00:00"
    message: Optional[str] = None


class AppointmentUpdate(BaseModel):
    date: Optional[str] = None
    message: Optional[str] = None
    is_confirm: Optional[bool] = None
    is_come: Optional[bool] = None


def _user_mini(u: User):
    return {"id": str(u.id), "full_name": u.full_name, "role": str(u.role),
            "avatar": u.avatar, "phone": u.phone}


def _out(a: TeacherAppointment):
    return {
        "id": str(a.id),
        "student": _user_mini(a.student) if a.student else None,
        "teacher": _user_mini(a.teacher) if a.teacher else None,
        "date": a.date.isoformat(),
        "message": a.message,
        "is_confirm": a.is_confirm,
        "is_come": a.is_come,
        "created_at": a.created_at.isoformat(),
    }


@router.get("")
async def list_appointments(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(TeacherAppointment)
        .options(
            selectinload(TeacherAppointment.student),
            selectinload(TeacherAppointment.teacher),
        )
        .order_by(TeacherAppointment.date.desc())
        .offset(skip).limit(limit)
    )
    role = str(getattr(current_user, "role", ""))
    if role == "student":
        q = q.where(TeacherAppointment.student_id == current_user.id)
    elif role in {"teacher", "assistant_teacher"}:
        q = q.where(TeacherAppointment.teacher_id == current_user.id)

    result = await db.execute(q)
    return [_out(a) for a in result.scalars().all()]


@router.get("/available-slots")
async def available_slots(
    teacher_id: Optional[str] = Query(None),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return booked appointment times so client can show free slots."""
    q = select(TeacherAppointment.date)
    if teacher_id:
        q = q.where(TeacherAppointment.teacher_id == uuid.UUID(teacher_id))
    q = q.where(TeacherAppointment.date >= datetime.now(timezone.utc))
    result = await db.execute(q)
    booked = [r[0].isoformat() for r in result.all()]
    return {"booked": booked}


@router.post("", status_code=201)
async def create_appointment(
    data: AppointmentCreate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    teacher_id = uuid.UUID(data.teacher_id)
    teacher_result = await db.execute(select(User).where(User.id == teacher_id, User.is_active == True))
    teacher = teacher_result.scalar_one_or_none()
    if not teacher:
        raise HTTPException(404, "O'qituvchi topilmadi")

    appt = TeacherAppointment(
        student_id=current_user.id,
        teacher_id=teacher_id,
        date=datetime.fromisoformat(data.date),
        message=data.message,
    )
    db.add(appt)
    await db.commit()

    result = await db.execute(
        select(TeacherAppointment)
        .options(selectinload(TeacherAppointment.student), selectinload(TeacherAppointment.teacher))
        .where(TeacherAppointment.id == appt.id)
    )
    return _out(result.scalar_one())


@router.patch("/{appointment_id}")
async def update_appointment(
    appointment_id: uuid.UUID,
    data: AppointmentUpdate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TeacherAppointment)
        .options(selectinload(TeacherAppointment.student), selectinload(TeacherAppointment.teacher))
        .where(TeacherAppointment.id == appointment_id)
    )
    appt = result.scalar_one_or_none()
    if not appt:
        raise HTTPException(404, "Topilmadi")

    role = str(getattr(current_user, "role", ""))
    if role == "student" and appt.student_id != current_user.id:
        raise HTTPException(403, "Ruxsat yo'q")
    if role in {"teacher", "assistant_teacher"} and appt.teacher_id != current_user.id:
        raise HTTPException(403, "Ruxsat yo'q")

    updates = data.model_dump(exclude_unset=True)
    if "date" in updates and updates["date"]:
        appt.date = datetime.fromisoformat(updates.pop("date"))
    for k, v in updates.items():
        setattr(appt, k, v)

    await db.commit()
    await db.refresh(appt)
    return _out(appt)


@router.delete("/{appointment_id}", status_code=204)
async def delete_appointment(
    appointment_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(TeacherAppointment).where(TeacherAppointment.id == appointment_id))
    appt = result.scalar_one_or_none()
    if not appt:
        raise HTTPException(404, "Topilmadi")
    role = str(getattr(current_user, "role", ""))
    if role == "student" and appt.student_id != current_user.id:
        raise HTTPException(403, "Ruxsat yo'q")
    await db.delete(appt)
    await db.commit()
