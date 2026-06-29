"""Har kuni ertalab barcha aktiv guruhlar uchun bugungi davomatni yaratish."""
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.group import Group, GroupStatus
from app.utils.attendance_generator import generate_attendance_for_group

logger = logging.getLogger(__name__)


async def run_daily_attendance(db: AsyncSession) -> int:
    """
    Barcha aktiv guruhlar uchun bugungi sana bo'yicha attendance yaratadi.
    Faqat guruh jadvalida bugun dars bo'lsa yaratiladi.
    Qaytaradi: yaratilgan yozuvlar umumiy soni.
    """
    today = date.today()
    result = await db.execute(
        select(Group).where(Group.status == GroupStatus.active)
    )
    groups = result.scalars().all()

    total = 0
    for group in groups:
        created = await generate_attendance_for_group(db, group, from_date=today, to_date=today)
        if created:
            logger.info(f"[daily] group={group.name}: {created} attendance yaratildi ({today})")
            total += created

    logger.info(f"[daily] Jami {total} ta attendance yaratildi ({today})")
    return total
