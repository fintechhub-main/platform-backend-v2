"""Yordamchi ustoz: ish jadvali, dam olish kunlari, bo'sh slotlar, kurslarga biriktirish."""
import uuid
from datetime import datetime, date as DateType, time as TimeType, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, and_, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.course import Course
from app.models.group import GroupStudent, Group
from app.models.appointment import TeacherAppointment
from app.models.assistant import AssistantCourse, AssistantAvailability, AssistantDayOff
from app.dependencies import get_current_user, require_permission, is_student
from app.utils.tz import TZ, local_now

router = APIRouter(prefix="/assistant", tags=["assistant"])

SLOT_MIN = 30          # har o'quvchiga ajratiladigan vaqt
ASSISTANT_ROLES = ("assistant_teacher",)


# ── Schemas ──────────────────────────────────────────────────────────────────

class AvailabilityIn(BaseModel):
    weekday: int                    # 0=Dushanba ... 6=Yakshanba
    start_time: str                 # "10:00"
    end_time: str                   # "19:00"
    break_start: Optional[str] = None
    break_end: Optional[str] = None
    is_active: bool = True


class DayOffIn(BaseModel):
    date: str                       # YYYY-MM-DD
    reason: Optional[str] = None


class CoursesIn(BaseModel):
    course_ids: List[str]


def _t(s: Optional[str]) -> Optional[TimeType]:
    if not s:
        return None
    h, m = s.split(":")[:2]
    return TimeType(int(h), int(m))


def _is_assistant(u) -> bool:
    return str(u.role) in ASSISTANT_ROLES


async def _assert_can_edit(assistant_id: uuid.UUID, current_user, db: AsyncSession):
    """O'zi yoki admin tahrirlay oladi."""
    role = str(current_user.role)
    if current_user.id == assistant_id:
        return
    if role in ("admin", "superadmin"):
        return
    raise HTTPException(403, "Ruxsat yo'q")


# ── Yordamchi ustozlar ro'yxati ──────────────────────────────────────────────

@router.get("/teachers")
async def list_assistants(
    only_my_courses: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Yordamchi ustozlar. O'quvchi uchun — o'z kursiga biriktirilganlari."""
    q = select(User).where(User.role.in_(ASSISTANT_ROLES), User.is_active == True)  # noqa: E712
    rows = (await db.execute(q.order_by(User.full_name))).scalars().all()

    # har biriga kurslarini biriktiramiz
    links = (await db.execute(
        select(AssistantCourse.assistant_id, AssistantCourse.course_id, Course.title)
        .join(Course, Course.id == AssistantCourse.course_id)
    )).all()
    by_assistant = {}
    for aid, cid, title in links:
        by_assistant.setdefault(str(aid), []).append({"id": str(cid), "title": title})

    my_course_ids = set()
    if is_student(current_user) and only_my_courses:
        my_course_ids = {str(c) for c in (await db.execute(
            select(Group.course_id).join(GroupStudent, GroupStudent.group_id == Group.id)
            .where(GroupStudent.student_id == current_user.id)
        )).scalars().all() if c}

    out = []
    for u in rows:
        courses = by_assistant.get(str(u.id), [])
        if my_course_ids:
            # faqat o'quvchining kursiga biriktirilganlar (biriktirilmaganlar hammaga ko'rinadi)
            if courses and not any(c["id"] in my_course_ids for c in courses):
                continue
        out.append({
            "id": str(u.id), "full_name": u.full_name, "phone": u.phone,
            "avatar": u.avatar, "courses": courses,
        })
    return out


# ── Ish jadvali ──────────────────────────────────────────────────────────────

@router.get("/{assistant_id}/availability")
async def get_availability(assistant_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                           _=Depends(get_current_user)):
    rows = (await db.execute(
        select(AssistantAvailability)
        .where(AssistantAvailability.assistant_id == assistant_id)
        .order_by(AssistantAvailability.weekday)
    )).scalars().all()
    return [{
        "weekday": r.weekday,
        "start_time": r.start_time.strftime("%H:%M"),
        "end_time": r.end_time.strftime("%H:%M"),
        "break_start": r.break_start.strftime("%H:%M") if r.break_start else None,
        "break_end": r.break_end.strftime("%H:%M") if r.break_end else None,
        "is_active": r.is_active,
    } for r in rows]


@router.put("/{assistant_id}/availability")
async def set_availability(assistant_id: uuid.UUID, items: List[AvailabilityIn],
                           db: AsyncSession = Depends(get_db),
                           current_user=Depends(get_current_user)):
    await _assert_can_edit(assistant_id, current_user, db)
    await db.execute(sa_delete(AssistantAvailability)
                     .where(AssistantAvailability.assistant_id == assistant_id))
    for it in items:
        db.add(AssistantAvailability(
            assistant_id=assistant_id, weekday=it.weekday,
            start_time=_t(it.start_time), end_time=_t(it.end_time),
            break_start=_t(it.break_start), break_end=_t(it.break_end),
            is_active=it.is_active,
        ))
    await db.commit()
    return {"ok": True, "count": len(items)}


# ── Dam olish kunlari ────────────────────────────────────────────────────────

@router.get("/{assistant_id}/day-off")
async def list_day_off(assistant_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                       _=Depends(get_current_user)):
    rows = (await db.execute(
        select(AssistantDayOff)
        .where(AssistantDayOff.assistant_id == assistant_id,
               AssistantDayOff.date >= local_now().date())
        .order_by(AssistantDayOff.date)
    )).scalars().all()
    return [{"date": r.date.isoformat(), "reason": r.reason} for r in rows]


@router.post("/{assistant_id}/day-off")
async def add_day_off(assistant_id: uuid.UUID, data: DayOffIn,
                      db: AsyncSession = Depends(get_db),
                      current_user=Depends(get_current_user)):
    await _assert_can_edit(assistant_id, current_user, db)
    d = DateType.fromisoformat(data.date)
    exists = (await db.execute(select(AssistantDayOff).where(and_(
        AssistantDayOff.assistant_id == assistant_id, AssistantDayOff.date == d)))).scalars().first()
    if exists:
        exists.reason = data.reason
    else:
        db.add(AssistantDayOff(assistant_id=assistant_id, date=d, reason=data.reason))
    await db.commit()
    return {"ok": True, "date": data.date}


@router.delete("/{assistant_id}/day-off/{day}")
async def remove_day_off(assistant_id: uuid.UUID, day: str,
                         db: AsyncSession = Depends(get_db),
                         current_user=Depends(get_current_user)):
    await _assert_can_edit(assistant_id, current_user, db)
    await db.execute(sa_delete(AssistantDayOff).where(and_(
        AssistantDayOff.assistant_id == assistant_id,
        AssistantDayOff.date == DateType.fromisoformat(day))))
    await db.commit()
    return {"ok": True}


# ── Bo'sh slotlar ────────────────────────────────────────────────────────────

async def free_slots_for(db: AsyncSession, assistant_id: uuid.UUID, day: DateType) -> List[str]:
    """Berilgan kun uchun bo'sh 30-daqiqalik slotlar (HH:MM ro'yxati)."""
    # dam olish kunimi?
    off = (await db.execute(select(AssistantDayOff).where(and_(
        AssistantDayOff.assistant_id == assistant_id,
        AssistantDayOff.date == day)))).scalars().first()
    if off:
        return []

    av = (await db.execute(select(AssistantAvailability).where(and_(
        AssistantAvailability.assistant_id == assistant_id,
        AssistantAvailability.weekday == day.weekday())))).scalars().first()
    if not av or not av.is_active:
        return []

    # o'sha kunga band qilinganlar (bekor qilinganlardan tashqari)
    start_dt = datetime.combine(day, TimeType(0, 0), tzinfo=TZ)
    end_dt = start_dt + timedelta(days=1)
    booked_rows = (await db.execute(select(TeacherAppointment.date).where(and_(
        TeacherAppointment.teacher_id == assistant_id,
        TeacherAppointment.date >= start_dt,
        TeacherAppointment.date < end_dt,
        (TeacherAppointment.is_confirm.is_(None)) | (TeacherAppointment.is_confirm.is_(True)),
    )))).scalars().all()
    # DB UTC qaytaradi — Toshkent vaqtiga o'girib solishtiramiz
    booked = {d.astimezone(TZ).strftime("%H:%M") for d in booked_rows}

    now = local_now()
    slots = []
    cur = datetime.combine(day, av.start_time, tzinfo=TZ)
    end = datetime.combine(day, av.end_time, tzinfo=TZ)
    bs = datetime.combine(day, av.break_start, tzinfo=TZ) if av.break_start else None
    be = datetime.combine(day, av.break_end, tzinfo=TZ) if av.break_end else None
    while cur + timedelta(minutes=SLOT_MIN) <= end:
        nxt = cur + timedelta(minutes=SLOT_MIN)
        in_break = bool(bs and be and not (nxt <= bs or cur >= be))
        hhmm = cur.strftime("%H:%M")
        if not in_break and hhmm not in booked and cur > now:
            slots.append(hhmm)
        cur = nxt
    return slots


@router.get("/{assistant_id}/slots")
async def get_slots(assistant_id: uuid.UUID, date: str = Query(...),
                    db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    day = DateType.fromisoformat(date)
    return {"date": date, "slot_minutes": SLOT_MIN,
            "slots": await free_slots_for(db, assistant_id, day)}


@router.get("/{assistant_id}/slots-range")
async def get_slots_range(assistant_id: uuid.UUID, days: int = Query(14, ge=1, le=60),
                          db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Kelgusi N kun uchun bo'sh slotlar — kalendar uchun."""
    today = local_now().date()
    out = []
    for i in range(days):
        d = today + timedelta(days=i)
        s = await free_slots_for(db, assistant_id, d)
        out.append({"date": d.isoformat(), "weekday": d.weekday(), "slots": s})
    return out


# ── Kurslarga biriktirish ────────────────────────────────────────────────────

@router.get("/{assistant_id}/courses")
async def get_assistant_courses(assistant_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                                _=Depends(get_current_user)):
    rows = (await db.execute(
        select(Course.id, Course.title).join(AssistantCourse, AssistantCourse.course_id == Course.id)
        .where(AssistantCourse.assistant_id == assistant_id)
    )).all()
    return [{"id": str(i), "title": t} for i, t in rows]


@router.put("/{assistant_id}/courses")
async def set_assistant_courses(assistant_id: uuid.UUID, data: CoursesIn,
                                db: AsyncSession = Depends(get_db),
                                _=Depends(require_permission("teachers", "update"))):
    await db.execute(sa_delete(AssistantCourse).where(AssistantCourse.assistant_id == assistant_id))
    for cid in data.course_ids:
        db.add(AssistantCourse(assistant_id=assistant_id, course_id=uuid.UUID(cid)))
    await db.commit()
    return {"ok": True, "count": len(data.course_ids)}
