"""Har kuni ertalab guruh Telegramiga kechagi davomatni yuborish."""
import html
import logging
from datetime import date, datetime, timedelta, timezone

import httpx
from sqlalchemy import select, and_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.group import Group, GroupStudent, GroupStatus
from app.models.attendance import Attendance
from app.models.user import User
from app.models.telegram_log import TelegramLog

logger = logging.getLogger(__name__)
# Davomat uchun alohida bot (@Fintech_davomat_bot); yo'q bo'lsa asosiy botga qaytadi
_BOT_TOKEN = settings.ATTENDANCE_BOT_TOKEN or settings.TELEGRAM_BOT_TOKEN
TELEGRAM_API = f"https://api.telegram.org/bot{_BOT_TOKEN}"

_PRESENT_STATUSES = {"present", "online", "late"}


def _status_of(att):
    """(qatnashdi_bool, 'online'|'offline', baho) qaytaradi."""
    if att is None:
        return False, "offline", 0
    s = str(att.status.value if hasattr(att.status, "value") else att.status)
    present = s in _PRESENT_STATUSES
    mode = "online" if s == "online" else "offline"
    grade = att.grade if att.grade is not None else 0
    return present, mode, grade


async def _fetch_rows(db: AsyncSession, group: Group, target_date: date):
    """Guruhning muzlatilmagan o'quvchilari + shu kungi davomati (bo'lmasa None)."""
    return (await db.execute(
        select(User, Attendance)
        .select_from(User)
        .join(GroupStudent, GroupStudent.student_id == User.id)
        .outerjoin(
            Attendance,
            and_(
                Attendance.student_id == User.id,
                Attendance.group_id == group.id,
                Attendance.date == target_date,
            ),
        )
        .where(GroupStudent.group_id == group.id)
        .where(GroupStudent.is_frozen == False)  # noqa: E712
        .order_by(User.full_name)
    )).all()


def _build_message(group_rows, target_date: date) -> str:
    header = (
        "📌 <b>Hurmatli ota-onalar!</b>\n\n"
        "Quyida sizga farzandingizning darsga qatnashuvi (davomati) haqida "
        "ma'lumot taqdim etilmoqda.\n\n"
        "✅ Darsga qatnashganlar — yashil belgi bilan\n"
        "❌ Qatnashmaganlar — qizil belgi bilan belgilanadi.\n\n"
        f"📅 Sana:  {target_date.strftime('%d.%m.%Y')}\n"
    )
    parts = [header]
    for i, (student, att) in enumerate(group_rows, 1):
        present, mode, grade = _status_of(att)
        mark = "✅" if present else "❌"
        name = html.escape(student.full_name or "—", quote=False)
        parts.append(f"\n{i}. {name} ({mode}){mark} \nSinf ishi: {grade} ball")
    parts.append(
        "\n\nFarzandingizning muntazam ishtiroki uning bilim va rivojlanishiga "
        "bevosita ta'sir qiladi. Doimiy hamkorlik uchun tashakkur!\n\n"
        "Hurmat bilan,\nFinTechHub o'quv markazi"
    )
    return "".join(parts)


async def send_group_attendance(db: AsyncSession, group: Group, target_date: date, force: bool = False):
    """
    Bitta guruh uchun target_date davomatini Telegramga yuboradi va log yozadi.
    Dublikatdan himoya: (group_id, log_date, kind) unique + claim — 2 worker yoki
    qayta ishga tushishda faqat bitta xabar ketadi. force=True (qo'lda qayta yuborish)
    mavjud logni yangilaydi.
    Qaytaradi: 'sent' | 'failed' | None (yuboradigan narsa yo'q / dublikat).
    """
    rows = await _fetch_rows(db, group, target_date)
    if not rows:
        return None
    # Shu kunga hech bo'lmasa bitta davomat yozuvi bo'lsagina yuboramiz
    if not any(att is not None for _, att in rows):
        return None

    text = _build_message(rows, target_date)

    # Claim — atomik. Faqat bitta worker bu (group, sana) uchun yozuv yaratadi.
    claim = (
        pg_insert(TelegramLog)
        .values(
            group_id=group.id, log_date=target_date, kind="attendance",
            status="sending",
            chat_id=str(group.chat_id) if group.chat_id else None,
            text=text,
        )
        .on_conflict_do_nothing(index_elements=["group_id", "log_date", "kind"])
        .returning(TelegramLog.id)
    )
    claimed_id = (await db.execute(claim)).scalar_one_or_none()
    await db.commit()

    if claimed_id is None:
        # Boshqa worker claim qildi yoki allaqachon yuborilgan
        if not force:
            return None
        existing = (await db.execute(
            select(TelegramLog).where(and_(
                TelegramLog.group_id == group.id,
                TelegramLog.log_date == target_date,
                TelegramLog.kind == "attendance",
            ))
        )).scalars().first()
        if existing is None:
            return None
        claimed_id = existing.id

    # Yuborish
    message_id = None
    if not group.chat_id:
        status, error = "failed", "Guruhda Telegram chat_id yo'q"
    else:
        payload = {"chat_id": group.chat_id, "text": text, "parse_mode": "HTML"}
        if group.attendance_topic_id:
            try:
                payload["message_thread_id"] = int(group.attendance_topic_id)
            except (ValueError, TypeError):
                pass
        status, error = "sent", None
        try:
            async with httpx.AsyncClient(timeout=25) as client:
                r = await client.post(f"{TELEGRAM_API}/sendMessage", json=payload)
                data = r.json()
                if not data.get("ok"):
                    status, error = "failed", str(data.get("description") or data)[:900]
                else:
                    message_id = str(data.get("result", {}).get("message_id") or "") or None
        except Exception as e:
            status, error = "failed", str(e)[:900]

    log = await db.get(TelegramLog, claimed_id)
    if log:
        log.status = status
        log.error = error
        log.text = text
        log.chat_id = str(group.chat_id) if group.chat_id else None
        if message_id:
            log.message_id = message_id
    await db.commit()
    return status


EDIT_WINDOW = timedelta(hours=48)


async def sync_group_attendance_message(db: AsyncSession, group_id, target_date: date):
    """Davomat platforma orqali o'zgartirilganda, agar shu (guruh, sana) uchun

    Telegramga xabar allaqachon yuborilgan bo'lsa va u 48 soatdan kam vaqt
    oldin yuborilgan bo'lsa — xabarni yangi ma'lumot bilan tahrirlaydi
    (masalan, adashib "kelmagan" qilib belgilangan o'quvchi "keldi" qilib
    to'g'irlansa). 48 soatdan o'tgan yoki umuman yuborilmagan bo'lsa — hech
    narsa qilmaydi. Xatolar yutiladi: bu ikkinchi darajali amal, davomatni
    saqlashning o'ziga xalaqit bermasligi kerak.
    """
    try:
        log = (await db.execute(select(TelegramLog).where(and_(
            TelegramLog.group_id == group_id,
            TelegramLog.log_date == target_date,
            TelegramLog.kind == "attendance",
            TelegramLog.status == "sent",
        )))).scalars().first()
        if not log or not log.message_id or not log.chat_id:
            return
        if datetime.now(timezone.utc) - log.created_at > EDIT_WINDOW:
            return

        group = await db.get(Group, group_id)
        if not group:
            return
        rows = await _fetch_rows(db, group, target_date)
        if not rows:
            return
        text = _build_message(rows, target_date)
        if text == log.text:
            return  # o'zgarish yo'q — bekorga Telegramga so'rov yubormaymiz

        payload = {"chat_id": log.chat_id, "message_id": int(log.message_id),
                   "text": text, "parse_mode": "HTML"}
        async with httpx.AsyncClient(timeout=25) as client:
            r = await client.post(f"{TELEGRAM_API}/editMessageText", json=payload)
            data = r.json()
            if data.get("ok"):
                log.text = text
                await db.commit()
            else:
                logger.warning(f"[attendance_telegram] edit muvaffaqiyatsiz: {data}")
    except Exception as e:
        logger.warning(f"[attendance_telegram] sync xato: {e}")


async def send_daily_attendance_telegram(db: AsyncSession, target_date: date | None = None) -> dict:
    """Barcha aktiv guruhlar uchun target_date (default: kecha) davomatini yuboradi."""
    if target_date is None:
        target_date = date.today() - timedelta(days=1)
    groups = (await db.execute(
        select(Group).where(Group.status == GroupStatus.active)
    )).scalars().all()

    sent = failed = skipped = 0
    for group in groups:
        try:
            res = await send_group_attendance(db, group, target_date)
        except Exception as e:
            logger.error(f"[attendance_telegram] group={group.name} xato: {e}")
            res = "failed"
        if res == "sent":
            sent += 1
        elif res == "failed":
            failed += 1
        else:
            skipped += 1

    result = {"date": str(target_date), "sent": sent, "failed": failed, "skipped": skipped}
    logger.info(f"[attendance_telegram] {result}")
    return result
