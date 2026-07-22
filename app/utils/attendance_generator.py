"""
Guruh jadvaliga qarab attendance yozuvlarini avtomatik yaratish.
Schedule format: "Du/Cho/Ju 09:00-11:00"
"""
import uuid
from datetime import date, timedelta
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.attendance import Attendance, AttendanceStatus
from app.models.group import Group, GroupStudent

# Uzbek day abbreviations → Python weekday (0=Monday)
DAY_MAP = {
    'du': 0, 'dush': 0, 'dushanba': 0,
    'se': 1, 'ses': 1, 'seshanba': 1,
    'ch': 2, 'cho': 2, 'chor': 2, 'chorshanba': 2,
    'pa': 3, 'pay': 3, 'payshanba': 3,
    'ju': 4, 'jum': 4, 'juma': 4,
    'sh': 5, 'sha': 5, 'shanba': 5,
    'ya': 6, 'yak': 6, 'yakshanba': 6,
}


def parse_schedule_days(schedule: str) -> List[int]:
    """'Du/Cho/Ju 09:00-11:00' → [0, 2, 4]"""
    if not schedule:
        return []
    # Faqat kun qismini olish (vaqtdan oldingi)
    days_part = schedule.split()[0] if schedule.split() else schedule
    weekdays = []
    for part in days_part.split('/'):
        key = part.strip().lower()
        if key in DAY_MAP:
            weekdays.append(DAY_MAP[key])
    return list(set(weekdays))


def lesson_dates_between(start: date, end: date, weekdays: List[int]) -> List[date]:
    """start dan end gacha weekdays kunlaridagi sanalar ro'yxati."""
    if not weekdays:
        return []
    dates = []
    current = start
    while current <= end:
        if current.weekday() in weekdays:
            dates.append(current)
        current += timedelta(days=1)
    return dates


async def generate_attendance_for_group(
    db: AsyncSession,
    group: Group,
    from_date: date | None = None,
    to_date: date | None = None,
) -> int:
    """
    Guruh uchun from_date..to_date oralig'ida attendance yozuvlari yaratadi.
    Mavjud yozuvlarni qayta yaratmaydi.
    Qaytaradi: yaratilgan yozuvlar soni.
    """
    if not group.schedule or not group.start_date:
        return 0

    today = date.today()
    start = from_date or group.start_date
    end = to_date or min(today, group.end_date or today)

    if start > end:
        return 0

    weekdays = parse_schedule_days(group.schedule)
    if not weekdays:
        return 0

    dates = lesson_dates_between(start, end, weekdays)
    if not dates:
        return 0

    # Guruh studentlarini olish
    students_res = await db.execute(
        select(GroupStudent.student_id).where(GroupStudent.group_id == group.id)
    )
    student_ids = students_res.scalars().all()
    if not student_ids:
        return 0

    # Mavjud attendance yozuvlarini olish (qayta yaratmaslik uchun)
    existing_res = await db.execute(
        select(Attendance.student_id, Attendance.date)
        .where(Attendance.group_id == group.id)
        .where(Attendance.date.in_(dates))
    )
    existing_set = {(str(r.student_id), r.date) for r in existing_res.all()}

    rows = []
    for lesson_date in dates:
        for student_id in student_ids:
            if (str(student_id), lesson_date) not in existing_set:
                rows.append({
                    "id": uuid.uuid4(),
                    "group_id": group.id,
                    "student_id": student_id,
                    "date": lesson_date,
                    "status": AttendanceStatus.absent,
                    "grade": None,
                })

    if rows:
        # ON CONFLICT DO NOTHING — bir vaqtda ishga tushsa ham duplikat yaratmaydi
        stmt = pg_insert(Attendance).values(rows).on_conflict_do_nothing(
            index_elements=["group_id", "student_id", "date"]
        )
        await db.execute(stmt)
        await db.commit()

    return len(rows)
