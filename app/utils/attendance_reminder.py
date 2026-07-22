"""Dars tugagach 15 daqiqadan keyin davomat qilinmagan bo'lsa ustozga eslatma."""
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.group import Group, GroupStudent
from app.models.attendance import Attendance
from app.services.teacher_bot import (
    tb_send, parse_schedule, reminder_already_sent, mark_reminder_sent,
)

logger = logging.getLogger(__name__)
TZ = ZoneInfo("Asia/Tashkent")

DELAY_MIN = 15        # dars tugagach necha daqiqadan keyin
MAX_LATE_HOURS = 6    # bundan kech bo'lsa yubormaymiz


async def run_attendance_reminder(db: AsyncSession) -> dict:
    now = datetime.now(TZ)
    today = now.date()
    wd = today.weekday()

    rows = (await db.execute(
        select(Group, User)
        .join(User, User.id == Group.teacher_id)
        .where(Group.status == "active")
        .where(User.telegram_id.isnot(None))
    )).all()

    sent = 0
    for g, teacher in rows:
        days, start_t, end_t = parse_schedule(g.schedule)
        if wd not in days or not end_t:
            continue
        end_dt = datetime.combine(today, end_t, tzinfo=TZ)
        if now < end_dt + timedelta(minutes=DELAY_MIN):
            continue
        if now > end_dt + timedelta(hours=MAX_LATE_HOURS):
            continue
        if await reminder_already_sent(str(g.id), today.isoformat()):
            continue

        att = (await db.execute(select(Attendance).where(and_(
            Attendance.group_id == g.id, Attendance.date == today)))).scalars().all()
        marked = any(
            str(a.status.value if hasattr(a.status, "value") else a.status) != "absent"
            for a in att
        )
        if marked:
            await mark_reminder_sent(str(g.id), today.isoformat())
            continue

        # Faqat eslatma matni — bot orqali davomat belgilash o'chirilgan
        date_str = today.strftime("%d.%m.%Y")
        lines = [
            "⚠️ <b>{}</b> — davomat qilinmagan.".format(g.name),
            "",
            "📅 Sana: {}".format(date_str),
        ]
        if g.schedule:
            lines.append("🕒 Dars vaqti: {}".format(g.schedule))
        if g.group_link:
            lines.append("🔗 Guruh linki: {}".format(g.group_link))
        lines.append("")
        lines.append("Iltimos, platformada davomatni belgilang.")

        # Kuniga faqat 1 marta: yuborishdan oldin belgilab qo'yamiz
        await mark_reminder_sent(str(g.id), today.isoformat())
        try:
            res = await tb_send(teacher.telegram_id, "\n".join(lines))
            if res.get("ok"):
                sent += 1
            else:
                logger.warning("[att_reminder] %s: %s", g.name, res.get("description"))
        except Exception as e:
            logger.error("[att_reminder] %s xato: %s", g.name, e)

    if sent:
        logger.info("[att_reminder] %s ta eslatma yuborildi", sent)
    return {"sent": sent}
