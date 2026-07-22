"""@ZiyoDevBot — ustozlar uchun bot: Telegram API yordamchilari va klaviaturalar."""
import json
import re
import secrets
from datetime import time as time_cls

import httpx

from app.config import settings
from app.redis_client import get_redis
from app.utils.attendance_generator import parse_schedule_days

TB_API = "https://api.telegram.org/bot{}".format(settings.TEACHER_BOT_TOKEN)

SESS_KEY = "tb_att:{}"          # sid -> attendance sessiya
SESS_TTL = 6 * 60 * 60          # 6 soat
REM_KEY = "tb_rem:{}:{}"        # group_id:sana -> eslatma yuborilgan
REM_TTL = 20 * 60 * 60

BTN_TODAY = "📅 Bugungi darslarim"
BTN_GROUPS = "👥 Guruhlarim"
BTN_BOOKINGS = "📌 Yozuvlarim"
BTN_DAYOFF = "🚫 Dam olish kunim"

MAIN_KB = {
    "keyboard": [[{"text": BTN_TODAY}], [{"text": BTN_GROUPS}]],
    "resize_keyboard": True,
}
# Yordamchi ustoz uchun: yozuvlar + dam olish kuni (ish vaqtini bot orqali tahrirlamaydi)
ASSISTANT_KB = {
    "keyboard": [[{"text": BTN_BOOKINGS}], [{"text": BTN_DAYOFF}]],
    "resize_keyboard": True,
}
PHONE_KB = {
    "keyboard": [[{"text": "📱 Telefon raqamni yuborish", "request_contact": True}]],
    "resize_keyboard": True,
    "one_time_keyboard": True,
}


# ── Telegram API ─────────────────────────────────────────────────────────────

async def tb_send(chat_id, text, reply_markup=None, parse_mode="HTML"):
    payload = {"chat_id": chat_id, "text": text[:4000], "parse_mode": parse_mode,
               "disable_web_page_preview": True}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    async with httpx.AsyncClient(timeout=25) as c:
        r = await c.post(TB_API + "/sendMessage", json=payload)
        return r.json()


async def tb_edit(chat_id, message_id, text, reply_markup=None, parse_mode="HTML"):
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text[:4000],
               "parse_mode": parse_mode, "disable_web_page_preview": True}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    async with httpx.AsyncClient(timeout=25) as c:
        r = await c.post(TB_API + "/editMessageText", json=payload)
        return r.json()


async def tb_delete(chat_id, message_id):
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(TB_API + "/deleteMessage",
                         json={"chat_id": chat_id, "message_id": message_id})
        return r.json()


async def tb_answer(callback_id, text=None, show_alert=False):
    payload = {"callback_query_id": callback_id, "show_alert": show_alert}
    if text:
        payload["text"] = text[:200]
    async with httpx.AsyncClient(timeout=20) as c:
        await c.post(TB_API + "/answerCallbackQuery", json=payload)


async def tb_set_webhook(base_url):
    url = "{}/api/v1/teacher-bot/webhook".format(base_url)
    async with httpx.AsyncClient(timeout=25) as c:
        r = await c.post(TB_API + "/setWebhook", json={"url": url})
        return r.json()


# ── Jadval ───────────────────────────────────────────────────────────────────

def parse_schedule(schedule):
    """'Du/Ch/Ju 19:00-21:00' -> (kunlar, boshlanish, tugash)."""
    if not schedule:
        return [], None, None
    days = parse_schedule_days(schedule)
    start = end = None
    m = re.search(r"(\d{1,2}):(\d{2})\s*[-–—]\s*(\d{1,2}):(\d{2})", schedule)
    if m:
        try:
            start = time_cls(int(m.group(1)), int(m.group(2)))
            end = time_cls(int(m.group(3)), int(m.group(4)))
        except ValueError:
            pass
    return days, start, end


# ── Davomat sessiyasi (Redis) ────────────────────────────────────────────────

async def create_att_session(group_id, group_name, date_str, students):
    """students: [{'id': str, 'name': str, 'status': 'K'|'Y'}] -> sid"""
    sid = secrets.token_urlsafe(6)
    r = await get_redis()
    await r.set(SESS_KEY.format(sid), json.dumps({
        "group_id": str(group_id),
        "group_name": group_name,
        "date": date_str,
        "students": students,
    }), ex=SESS_TTL)
    return sid


async def get_att_session(sid):
    r = await get_redis()
    raw = await r.get(SESS_KEY.format(sid))
    if not raw:
        return None
    return json.loads(raw)


async def save_att_session(sid, data):
    r = await get_redis()
    await r.set(SESS_KEY.format(sid), json.dumps(data), ex=SESS_TTL)


# ── Umumiy sessiya (o'quvchi chiqarish uchun) ────────────────────────────────

async def create_session(data):
    sid = secrets.token_urlsafe(6)
    r = await get_redis()
    await r.set(SESS_KEY.format(sid), json.dumps(data), ex=SESS_TTL)
    return sid


async def get_session(sid):
    r = await get_redis()
    raw = await r.get(SESS_KEY.format(sid))
    return json.loads(raw) if raw else None


async def save_session(sid, data):
    r = await get_redis()
    await r.set(SESS_KEY.format(sid), json.dumps(data), ex=SESS_TTL)


def remove_keyboard(sid, students):
    """O'quvchilar ro'yxati — belgilangani ❌ bilan, pastda saqlash/ortga."""
    rows = []
    for i, s in enumerate(students):
        mark = "❌ " if s.get("marked") else ""
        rows.append([{"text": "{}{}".format(mark, s["name"][:40]),
                      "callback_data": "rs:{}:{}".format(sid, i)}])
    rows.append([{"text": "💾 Saqlash", "callback_data": "rsv:{}".format(sid)}])
    rows.append([{"text": "⬅️ Ortga", "callback_data": "del"}])
    return {"inline_keyboard": rows}


def remove_text(group_name, students):
    marked = [s["name"] for s in students if s.get("marked")]
    lines = [
        "👥 <b>{}</b> — o'quvchilarni guruhdan chiqarish".format(group_name),
        "",
        "Chiqarmoqchi bo'lganingizni bosing (❌ bo'ladi), so'ng <b>Saqlash</b>ni bosing.",
    ]
    if marked:
        lines.append("")
        lines.append("❌ Belgilangan ({} ta): {}".format(len(marked), ", ".join(marked[:10])))
    return "\n".join(lines)


async def reminder_already_sent(group_id, date_str):
    r = await get_redis()
    return bool(await r.get(REM_KEY.format(group_id, date_str)))


async def mark_reminder_sent(group_id, date_str):
    r = await get_redis()
    await r.set(REM_KEY.format(group_id, date_str), "1", ex=REM_TTL)


# ── Davomat klaviaturasi ─────────────────────────────────────────────────────

def att_keyboard(sid, students):
    """Har o'quvchi uchun: [ism] [K] [Y] — tanlanganida ✅."""
    rows = []
    for i, s in enumerate(students):
        k = "K ✅" if s["status"] == "K" else "K"
        y = "Y ✅" if s["status"] == "Y" else "Y"
        rows.append([
            {"text": s["name"][:22], "callback_data": "n:{}".format(sid)},
            {"text": k, "callback_data": "m:{}:{}:K".format(sid, i)},
            {"text": y, "callback_data": "m:{}:{}:Y".format(sid, i)},
        ])
    rows.append([{"text": "✅ Barchani \"Keldi\" qilish", "callback_data": "all:{}".format(sid)}])
    rows.append([{"text": "💾 O'zgarishlarni saqlash", "callback_data": "sv:{}".format(sid)}])
    return {"inline_keyboard": rows}


def att_text(group_name, link, schedule, date_str, saved=False):
    lines = []
    if saved:
        lines.append("✅ <b>Davomat saqlandi</b>\n")
    else:
        lines.append("⚠️ <b>{}</b> — davomat qilinmagan.\n".format(group_name))
    lines.append("📅 Sana: {}".format(date_str))
    if schedule:
        lines.append("🕒 Dars vaqti: {}".format(schedule))
    if link:
        lines.append("🔗 Guruh linki: {}".format(link))
    if not saved:
        lines.append("\nQuyidan har bir o'quvchini belgilang va saqlang:")
    return "\n".join(lines)


# ── Kutish holati (matn kutilayotgan amallar uchun) ──────────────────────────

WAIT_KEY = "tb_wait:{}"
WAIT_TTL = 20 * 60


async def set_wait(chat_id, payload):
    r = await get_redis()
    await r.set(WAIT_KEY.format(chat_id), json.dumps(payload), ex=WAIT_TTL)


async def get_wait(chat_id):
    r = await get_redis()
    raw = await r.get(WAIT_KEY.format(chat_id))
    return json.loads(raw) if raw else None


async def clear_wait(chat_id):
    r = await get_redis()
    await r.delete(WAIT_KEY.format(chat_id))
