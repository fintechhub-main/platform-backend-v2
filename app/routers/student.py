"""O'quvchining shaxsiy ma'lumotlari: dashboard, kalendar, davomat.

Bu yerdagi barcha endpointlar faqat so'rov yuborgan o'quvchining o'z ma'lumotini
qaytaradi — guruhdagi boshqa o'quvchilar ko'rinmaydi. Shu sabab guruh bo'yicha
ishlaydigan /attendance endpointlari o'quvchiga ochilmaydi.
"""
import uuid
from datetime import date as DateType, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.attendance import Attendance
from app.models.course import Course
from app.models.event import Event
from app.models.group import Group, GroupStudent
from app.models.group_progress import GroupLessonDone
from app.models.lesson import Lesson, Module
from app.models.lesson_homework import LessonHomework, LessonHomeworkSubmission, SubmissionStatus
from app.models.user import User
from app.utils.attendance_generator import parse_schedule_days
from app.utils.tz import local_now
from app.utils.student_scope import open_lesson_ids

router = APIRouter(prefix="/student", tags=["student"])

UZ_DAYS = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]


def _status_str(a) -> Optional[str]:
    if not a or not a.status:
        return None
    return a.status.value if hasattr(a.status, "value") else str(a.status)


async def _my_groups(db: AsyncSession, student_id):
    rows = (await db.execute(
        select(Group, Course, User)
        .join(GroupStudent, GroupStudent.group_id == Group.id)
        .outerjoin(Course, Course.id == Group.course_id)
        .outerjoin(User, User.id == Group.teacher_id)
        .where(GroupStudent.student_id == student_id)
    )).all()
    return rows


@router.get("/attendance")
async def my_attendance(
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """O'quvchining o'z davomati va baholari."""
    q = (select(Attendance, Group.name)
         .outerjoin(Group, Group.id == Attendance.group_id)
         .where(Attendance.student_id == current_user.id))
    if date_from:
        q = q.where(Attendance.date >= DateType.fromisoformat(date_from))
    if date_to:
        q = q.where(Attendance.date <= DateType.fromisoformat(date_to))
    rows = (await db.execute(q.order_by(Attendance.date.desc()))).all()
    return [{
        "id": str(a.id),
        "date": a.date.isoformat(),
        "group_id": str(a.group_id),
        "group_name": gname,
        "status": _status_str(a),
        "grade": a.grade,
        "reason": a.reason,
    } for a, gname in rows]


@router.get("/overview")
async def student_overview(
    month: Optional[str] = Query(None, description="YYYY-MM — kalendar oyi"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Dashboard uchun: umumiy ma'lumot, kalendar, baholar, tadbirlar."""
    today = local_now().date()
    if month:
        y, m = (int(x) for x in month.split("-")[:2])
    else:
        y, m = today.year, today.month
    first = DateType(y, m, 1)
    last = DateType(y + (m == 12), (m % 12) + 1, 1) - timedelta(days=1)

    groups = await _my_groups(db, current_user.id)

    # ── Davomat (butun tarix — statistika uchun) ─────────────────────────────
    att_rows = (await db.execute(
        select(Attendance).where(Attendance.student_id == current_user.id)
    )).scalars().all()
    by_date = {a.date: a for a in att_rows}

    present = sum(1 for a in att_rows if _status_str(a) == "present")
    absent = sum(1 for a in att_rows if _status_str(a) == "absent")
    late = sum(1 for a in att_rows if _status_str(a) == "late")
    total_marked = present + absent + late
    grades = [a.grade for a in att_rows if a.grade is not None]

    # ── Uy vazifalar ────────────────────────────────────────────────────────
    open_ids = await open_lesson_ids(db, current_user.id)

    hw_total = 0
    hw_done = 0
    hw_scores = []
    if open_ids:
        hw_ids = (await db.execute(
            select(LessonHomework.id).where(LessonHomework.lesson_id.in_(open_ids))
        )).scalars().all()
        hw_total = len(hw_ids)
        if hw_ids:
            subs = (await db.execute(
                select(LessonHomeworkSubmission).where(
                    LessonHomeworkSubmission.student_id == current_user.id,
                    LessonHomeworkSubmission.homework_id.in_(hw_ids))
            )).scalars().all()
            hw_done = sum(1 for s in subs if s.status != SubmissionStatus.pending)
            hw_scores = [s.score for s in subs if s.score is not None]

    # ── Kalendar: dars kunlari + tadbirlar + dam olish ──────────────────────
    # Har guruhning jadvalidan haftaning qaysi kunlari dars borligini olamiz
    lesson_weekdays = {}          # weekday -> [(guruh nomi, jadval)]
    for g, course, teacher in groups:
        for wd in parse_schedule_days(g.schedule or ""):
            lesson_weekdays.setdefault(wd, []).append((g.name, g.schedule or ""))

    events = (await db.execute(
        select(Event).where(and_(Event.event_date >= first, Event.event_date <= last,
                                 Event.is_active == True))  # noqa: E712
    )).scalars().all()
    events_by_date = {}
    for e in events:
        events_by_date.setdefault(e.event_date, []).append(e)

    calendar = []
    d = first
    while d <= last:
        att = by_date.get(d)
        day_groups = lesson_weekdays.get(d.weekday(), [])
        day_events = events_by_date.get(d, [])
        calendar.append({
            "date": d.isoformat(),
            "weekday": d.weekday(),
            "is_today": d == today,
            "has_lesson": bool(day_groups),
            "is_rest_day": not day_groups,        # dars yo'q kun
            "lessons": [{"group": n, "schedule": s} for n, s in day_groups],
            "attendance": _status_str(att),
            "grade": att.grade if att else None,
            "reason": att.reason if att else None,
            "events": [{"id": str(e.id), "title": e.title,
                        "time": e.event_time, "location": e.location} for e in day_events],
        })
        d += timedelta(days=1)

    # ── So'nggi baholar ─────────────────────────────────────────────────────
    recent = sorted([a for a in att_rows if a.grade is not None],
                    key=lambda a: a.date, reverse=True)[:10]
    gname = {str(g.id): g.name for g, _c, _t in groups}

    return {
        "profile": {
            "id": str(current_user.id),
            "full_name": current_user.full_name,
            "phone": current_user.phone,
            "avatar": current_user.avatar,
        },
        "groups": [{
            "id": str(g.id), "name": g.name,
            "course": c.title if c else None,
            "teacher": t.full_name if t else None,
            "schedule": g.schedule,
        } for g, c, t in groups],
        "stats": {
            "attendance_percent": round(present * 100 / total_marked) if total_marked else None,
            "present": present, "absent": absent, "late": late,
            "avg_grade": round(sum(grades) / len(grades), 1) if grades else None,
            "grades_count": len(grades),
            "homework_done": hw_done,
            "homework_total": hw_total,
            "homework_avg": round(sum(hw_scores) / len(hw_scores), 1) if hw_scores else None,
            "lessons_open": len(open_ids),
        },
        "month": f"{y:04d}-{m:02d}",
        "calendar": calendar,
        "recent_grades": [{
            "date": a.date.isoformat(),
            "grade": a.grade,
            "group": gname.get(str(a.group_id)),
            "reason": a.reason,
        } for a in recent],
        "upcoming_events": [{
            "id": str(e.id), "title": e.title, "date": e.event_date.isoformat(),
            "time": e.event_time, "location": e.location,
        } for e in sorted(events, key=lambda x: x.event_date) if e.event_date >= today][:5],
    }
