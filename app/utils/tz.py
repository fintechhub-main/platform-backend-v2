"""Vaqt mintaqasi — ko'rsatiladigan va hisoblanadigan vaqtlar Toshkent bo'yicha.

Baza ustunlari `timestamptz` (UTC saqlanadi), asyncpg ularni UTC tzinfo bilan
qaytaradi. To'g'ridan-to'g'ri strftime qilinsa vaqt 5 soat orqada ko'rinadi,
shuning uchun ko'rsatishdan oldin har doim shu yerdagi funksiyalardan foydalaning.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Tashkent")


def local_now() -> datetime:
    """Hozirgi vaqt (Toshkent, tz bilan)."""
    return datetime.now(TZ)


def to_local(dt):
    """Bazadan kelgan vaqtni Toshkent vaqtiga o'giradi."""
    if dt is None:
        return None
    if dt.tzinfo is None:          # mintaqasiz kelsa — Toshkent deb qaraymiz
        return dt.replace(tzinfo=TZ)
    return dt.astimezone(TZ)


def fmt(dt, pattern: str = "%d.%m.%Y %H:%M") -> str:
    """Ko'rsatish uchun formatlash (Toshkent vaqtida)."""
    d = to_local(dt)
    return d.strftime(pattern) if d else "—"


def parse_local(s: str) -> datetime:
    """ISO sanani o'qiydi; mintaqa ko'rsatilmagan bo'lsa Toshkent deb hisoblaydi."""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt
