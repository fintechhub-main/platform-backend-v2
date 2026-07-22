"""Student mobile app API — /api/v1/student/* endpoints."""
import uuid
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import Optional

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.group import Group, GroupStudent
from app.models.course import Course
from app.models.attendance import Attendance

router = APIRouter(prefix="/student", tags=["student-app"])


def _require_student(current_user=Depends(get_current_user)):
    return current_user


@router.get("/home/")
async def student_home(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Student home screen data — shaped to match the legacy API."""
    # Active group + course
    gs_row = (await db.execute(
        select(GroupStudent, Group, Course)
        .join(Group, Group.id == GroupStudent.group_id)
        .join(Course, Course.id == Group.course_id)
        .where(
            GroupStudent.student_id == current_user.id,
            Group.status == "active",
            GroupStudent.is_frozen == False,
        )
        .order_by(Group.start_date.desc())
        .limit(1)
    )).first()

    group: Optional[Group] = gs_row[1] if gs_row else None
    course: Optional[Course] = gs_row[2] if gs_row else None

    course_name = course.title if course else ""
    group_name = group.name if group else ""

    # Parse schedule "Du/Ch/Ju 14:00-16:00"
    lesson_start = ""
    lesson_end = ""
    lesson_days: list[int] = []
    if group and group.schedule:
        parts = group.schedule.split(" ")
        if len(parts) >= 2:
            time_part = parts[-1]
            if "-" in time_part:
                times = time_part.split("-")
                lesson_start = times[0]
                lesson_end = times[1] if len(times) > 1 else ""
        day_map = {"Du": 1, "Se": 2, "Ch": 3, "Pa": 4, "Ju": 5, "Sh": 6, "Ya": 7}
        days_str = parts[0] if parts else ""
        for d in days_str.split("/"):
            if d in day_map:
                lesson_days.append(day_map[d])

    # Teacher
    teacher_name = ""
    if group and group.teacher_id:
        t = (await db.execute(
            select(User.full_name).where(User.id == group.teacher_id)
        )).scalar_one_or_none()
        if t:
            teacher_name = t

    # Attendance last 30 days
    since = date.today() - timedelta(days=30)
    att_rows = []
    if group:
        att_rows = (await db.execute(
            select(Attendance)
            .where(
                Attendance.student_id == current_user.id,
                Attendance.group_id == group.id,
                Attendance.date >= since,
            )
            .order_by(Attendance.date)
        )).scalars().all()

    lesson_scores: dict[str, int] = {}
    lesson_absence_reasons: dict[str, str] = {}
    unjoin_lesson = 0
    for a in att_rows:
        d_str = a.date.isoformat()
        if a.grade is not None:
            lesson_scores[d_str] = a.grade
        if str(a.status) in ("absent", "late"):
            unjoin_lesson += 1
        if a.reason:
            lesson_absence_reasons[d_str] = a.reason

    # Coins
    coin_balance = 0
    try:
        from app.models.coin import CoinTransaction
        coin_result = (await db.execute(
            select(func.coalesce(func.sum(CoinTransaction.amount), 0))
            .where(CoinTransaction.user_id == current_user.id)
        )).scalar()
        coin_balance = int(coin_result or 0)
    except Exception:
        pass

    # Payments debt
    unpayed_month = False
    unpayed_month_list: list = []
    try:
        from app.models.payment import Payment, PaymentType
        debt_rows = (await db.execute(
            select(Payment)
            .where(
                Payment.student_id == current_user.id,
                Payment.payment_type == PaymentType.monthly,
            )
            .order_by(Payment.date.desc())
            .limit(3)
        )).scalars().all()
        if not debt_rows:
            unpayed_month = True
    except Exception:
        pass

    student = current_user
    return {
        "id": str(student.id),
        "home_work_not_done_count": 0,
        "course_name": course_name,
        "lesson_start_time": lesson_start,
        "lesson_end_time": lesson_end,
        "unjoin_lesson": unjoin_lesson,
        "home_work_count": 0,
        "group_start_date": group.start_date.isoformat() if group and group.start_date else "",
        "student_teacher_name": teacher_name,
        "coin": coin_balance,
        "balls": 0,
        "attendance_balls": 0,
        "student": {
            "id": str(student.id),
            "full_name": student.full_name or "",
            "phone_number": student.phone or "",
            "email": student.email or "",
            "photo": student.avatar or "",
            "gender": student.gender or "",
            "birth_date": student.birth_date.isoformat() if student.birth_date else "",
            "proficiency_level": "",
            "group_name": group_name,
        },
        "unpayed_month": unpayed_month,
        "unpayed_month_list": unpayed_month_list,
        "proficiency_level": "",
        "top_students": [],
        "lesson_days": lesson_days,
        "lesson_scores": lesson_scores,
        "lesson_absence_reasons": lesson_absence_reasons,
        "lesson_topics_by_date": {},
        "lesson_times_by_date": {},
        "attendances_list": [
            {
                "date": a.date.isoformat(),
                "status": str(a.status),
                "grade": a.grade,
                "reason": a.reason or "",
            }
            for a in att_rows
        ],
        "calendar": {
            "day_of_week": lesson_days,
        },
    }
