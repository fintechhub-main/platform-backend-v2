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
from app.models.assistant import AssistantDayOff, AssistantAvailability
from app.services.notify import notify_user
from app.services.teacher_bot import tb_send
from app.utils.tz import fmt, parse_local
from app.models.user import User

router = APIRouter(prefix="/appointments", tags=["appointments"])


class AppointmentCreate(BaseModel):
    teacher_id: str
    date: str  # ISO format: "2025-07-15T10:00:00"
    message: Optional[str] = None


class AppointmentUpdate(BaseModel):
    cancel_reason: Optional[str] = None
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
        "cancel_reason": a.cancel_reason,
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

    when = parse_local(data.date)

    # Dam olish kuni yoki band slotga yozilmasin
    off = (await db.execute(select(AssistantDayOff).where(
        AssistantDayOff.assistant_id == teacher_id,
        AssistantDayOff.date == when.date()))).scalars().first()
    if off:
        raise HTTPException(400, "Bu kuni yordamchi ustoz dam oladi")
    busy = (await db.execute(select(TeacherAppointment).where(
        TeacherAppointment.teacher_id == teacher_id,
        TeacherAppointment.date == when,
        (TeacherAppointment.is_confirm.is_(None)) | (TeacherAppointment.is_confirm.is_(True)),
    ))).scalars().first()
    if busy:
        raise HTTPException(400, "Bu vaqt allaqachon band")

    appt = TeacherAppointment(
        student_id=current_user.id,
        teacher_id=teacher_id,
        date=when,
        message=data.message,
    )
    db.add(appt)
    await db.commit()

    # Yordamchi ustozga xabar (Telegram + ilova ichida)
    when_s = fmt(when)
    try:
        await notify_user(db, teacher_id, "Yangi yozuv",
                          f"{current_user.full_name} — {when_s}",
                          notification_type="appointment")
    except Exception:
        pass
    if teacher.telegram_id:
        txt = (f"📌 <b>Yangi yozuv</b>\n\n"
               f"👤 O'quvchi: {current_user.full_name}\n"
               f"🕒 Vaqt: {when_s}\n")
        if data.message:
            txt += f"💬 Izoh: {data.message}\n"
        txt += "\nTasdiqlash yoki bekor qilish uchun /start → Yozuvlarim"
        try:
            await tb_send(teacher.telegram_id, txt)
        except Exception:
            pass

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
    if role == "student":
        # O'quvchi o'z yozuvini faqat bekor qila oladi yoki matnini tahrirlaydi —
        # tasdiqlash va "keldi" belgisi yordamchi ustozning ixtiyorida.
        if updates.get("is_confirm") is True:
            raise HTTPException(403, "Yozuvni faqat yordamchi ustoz tasdiqlaydi")
        if "is_come" in updates:
            raise HTTPException(403, "Ruxsat yo'q")
    if "date" in updates and updates["date"]:
        appt.date = parse_local(updates.pop("date"))
    # Bekor qilinsa — sabab majburiy
    if updates.get("is_confirm") is False and not (updates.get("cancel_reason") or appt.cancel_reason):
        raise HTTPException(400, "Bekor qilish sababini yozing")
    for k, v in updates.items():
        setattr(appt, k, v)

    await db.commit()

    # O'quvchiga natijani bildiramiz
    if "is_confirm" in updates and updates["is_confirm"] is not None:
        when_s = fmt(appt.date)
        if updates["is_confirm"]:
            title, body = "Yozuvingiz tasdiqlandi ✅", f"{when_s} — yordamchi ustoz tasdiqladi"
        else:
            title = "Yozuvingiz bekor qilindi ❌"
            body = f"{when_s} — sabab: {updates.get('cancel_reason') or appt.cancel_reason or '—'}"
        try:
            await notify_user(db, appt.student_id, title, body, notification_type="appointment")
        except Exception:
            pass
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
