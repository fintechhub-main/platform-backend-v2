"""Scheduled push notification jobs."""
import logging
import re
from datetime import date, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import AsyncSessionLocal as async_session
from app.models.group import Group, GroupStudent
from app.models.payment import Payment
from app.models.user import User
from app.services.notify import notify_user

logger = logging.getLogger(__name__)

DAYS_MAP = {
    "Du": 0, "Se": 1, "Ch": 2, "Pa": 3, "Ju": 4, "Sh": 5, "Ya": 6,
    "Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6,
}


def _parse_schedule(schedule: str):
    """Parse 'Du/Ju/Ch 12:00-14:00' → (day_nums, start_hour, start_min)."""
    if not schedule:
        return None
    parts = schedule.strip().split()
    time_part = None
    day_nums = []
    for part in parts:
        m = re.match(r"(\d{1,2}):(\d{2})", part)
        if m:
            time_part = (int(m.group(1)), int(m.group(2)))
            break
    if not time_part:
        return None
    if len(parts) > 1 and "/" in parts[0]:
        for abbr in parts[0].split("/"):
            if abbr in DAYS_MAP:
                day_nums.append(DAYS_MAP[abbr])
    return (day_nums or None, time_part[0], time_part[1])


async def run_class_reminder():
    """Every 5 min: notify students whose class starts in 55-65 minutes."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).astimezone()
    now_min = now.hour * 60 + now.minute
    today_weekday = now.weekday()

    async with async_session() as db:
        try:
            result = await db.execute(
                select(Group).where(Group.status == "active", Group.schedule.isnot(None))
            )
            groups = result.scalars().all()

            for group in groups:
                parsed = _parse_schedule(group.schedule)
                if not parsed:
                    continue
                day_nums, start_h, start_m = parsed
                class_min = start_h * 60 + start_m
                diff = class_min - now_min

                is_today = (day_nums is None) or (today_weekday in day_nums)
                if not is_today:
                    continue
                if not (55 <= diff <= 65):
                    continue

                students = await db.execute(
                    select(GroupStudent.student_id).where(
                        GroupStudent.group_id == group.id,
                        GroupStudent.is_frozen == False,
                    )
                )
                student_ids = [r[0] for r in students.all()]
                for sid in student_ids:
                    await notify_user(
                        db, sid,
                        title="Dars 1 soatdan keyin boshlanadi! 📚",
                        body=f"{group.name} guruhi — {start_h:02d}:{start_m:02d}",
                        notification_type="class_reminder",
                        data={"group_id": str(group.id)},
                    )
            await db.commit()
        except Exception as e:
            logger.error(f"class_reminder error: {e}")


async def run_payment_reminder():
    """Daily 09:00: payment reminders — 5 days before, on day, overdue."""
    today = date.today()

    async with async_session() as db:
        try:
            result = await db.execute(
                select(Group).where(Group.status == "active", Group.payment_day.isnot(None))
            )
            groups = result.scalars().all()

            for group in groups:
                payment_day = group.payment_day
                try:
                    due = today.replace(day=payment_day)
                except ValueError:
                    import calendar
                    last_day = calendar.monthrange(today.year, today.month)[1]
                    due = today.replace(day=last_day)

                days_left = (due - today).days

                if days_left not in (5, 0) and days_left >= 0:
                    continue
                if days_left < 0 and today.weekday() == 0:
                    pass
                elif days_left < 0:
                    pass

                month_start = today.replace(day=1)
                if today.month == 12:
                    month_end = today.replace(year=today.year + 1, month=1, day=1)
                else:
                    month_end = today.replace(month=today.month + 1, day=1)

                students = await db.execute(
                    select(GroupStudent.student_id).where(
                        GroupStudent.group_id == group.id,
                        GroupStudent.is_frozen == False,
                    )
                )
                student_ids = [r[0] for r in students.all()]

                for sid in student_ids:
                    paid = await db.execute(
                        select(Payment).where(
                            Payment.student_id == sid,
                            Payment.group_id == group.id,
                            Payment.date >= month_start,
                            Payment.date < month_end,
                        )
                    )
                    if paid.scalar_one_or_none():
                        continue

                    if days_left == 5:
                        title = "To'lovga 5 kun qoldi ⚠️"
                        body = f"{group.name} — {due.strftime('%d.%m.%Y')} gacha to'lov qiling"
                        ntype = "payment_reminder"
                    elif days_left == 0:
                        title = "Bugun to'lov kuni 💰"
                        body = f"{group.name} — bugun to'lov muddati"
                        ntype = "payment_due"
                    else:
                        title = "To'lov muddati o'tdi ❗"
                        body = f"{group.name} — {abs(days_left)} kun kechikdi, iltimos to'lang"
                        ntype = "payment_overdue"

                    await notify_user(
                        db, sid, title=title, body=body,
                        notification_type=ntype,
                        data={"group_id": str(group.id), "days_left": str(days_left)},
                    )

            await db.commit()
        except Exception as e:
            logger.error(f"payment_reminder error: {e}")
