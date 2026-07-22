"""@ZiyoDevBot webhook — ustozlar uchun."""
import logging
import re
import uuid as uuid_mod
from datetime import date as date_cls, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, and_, delete as sa_delete, update as sa_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.group import Group, GroupStudent
from app.models.attendance import Attendance, AttendanceStatus
from app.models.appointment import TeacherAppointment
from app.models.assistant import AssistantDayOff
from app.models.lesson_homework import (
    LessonHomework, LessonHomeworkSubmission, SubmissionStatus)
from app.services.notify import notify_user
from app.services import hw_grader
from app.utils.tz import fmt, to_local, local_now
from app.utils.auth import hash_password
from app.redis_client import get_redis
from app.services.teacher_bot import (
    tb_send, tb_edit, tb_answer, tb_delete, parse_schedule,
    MAIN_KB, ASSISTANT_KB, PHONE_KB, BTN_TODAY, BTN_GROUPS, BTN_BOOKINGS, BTN_DAYOFF,
    set_wait, get_wait, clear_wait,
    create_session, get_session, save_session,
    remove_keyboard, remove_text,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/teacher-bot", tags=["teacher-bot"])

UZ_DAYS = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]


async def _user_by_chat(db: AsyncSession, chat_id):
    res = await db.execute(select(User).where(
        User.telegram_id == str(chat_id), User.is_active == True))  # noqa: E712
    return res.scalars().first()


async def _teacher_by_chat(db: AsyncSession, chat_id):
    u = await _user_by_chat(db, chat_id)
    if u and str(u.role) in ("teacher", "assistant_teacher"):
        return u
    return None


async def _teacher_groups(db: AsyncSession, teacher_id):
    res = await db.execute(select(Group).where(
        Group.teacher_id == teacher_id, Group.status == "active").order_by(Group.name))
    return res.scalars().all()


async def _group_students(db: AsyncSession, group_id):
    res = await db.execute(
        select(User).join(GroupStudent, GroupStudent.student_id == User.id)
        .where(GroupStudent.group_id == group_id, GroupStudent.is_frozen == False)  # noqa: E712
        .order_by(User.full_name)
    )
    return res.scalars().all()


async def _open_attendance(db, chat_id, group, message_id=None):
    """Guruh uchun bugungi davomat klaviaturasini ochadi."""
    today = date_cls.today()
    students = await _group_students(db, group.id)
    if not students:
        await tb_send(chat_id, "Bu guruhda o'quvchi yo'q.")
        return
    att_res = await db.execute(select(Attendance).where(and_(
        Attendance.group_id == group.id, Attendance.date == today)))
    cur = {str(a.student_id): a for a in att_res.scalars().all()}
    items = []
    for s in students[:30]:
        a = cur.get(str(s.id))
        st = "K" if (a and str(a.status.value if hasattr(a.status, "value") else a.status)
                     in ("present", "online", "late")) else "Y"
        items.append({"id": str(s.id), "name": s.full_name or "—", "status": st})
    sid = await create_att_session(group.id, group.name, today.strftime("%d.%m.%Y"), items)
    text = att_text(group.name, group.group_link, group.schedule, today.strftime("%d.%m.%Y"))
    kb = att_keyboard(sid, items)
    if message_id:
        await tb_edit(chat_id, message_id, text, kb)
    else:
        await tb_send(chat_id, text, kb)


async def _save_attendance(db, group_id, date_obj, students):
    for s in students:
        st = AttendanceStatus.present if s["status"] == "K" else AttendanceStatus.absent
        res = await db.execute(select(Attendance).where(and_(
            Attendance.group_id == uuid_mod.UUID(str(group_id)),
            Attendance.student_id == uuid_mod.UUID(s["id"]),
            Attendance.date == date_obj)))
        att = res.scalars().first()
        if att:
            att.status = st
            if st == AttendanceStatus.absent:
                att.grade = None
        else:
            db.add(Attendance(group_id=uuid_mod.UUID(str(group_id)),
                              student_id=uuid_mod.UUID(s["id"]),
                              date=date_obj, status=st))
    await db.commit()


def _su_key(chat_id):
    """Student-registration wizard holati alohida nomfazoda saqlanadi —
    ustozning tb_wait (masalan cancel_reason) holati bilan aralashmasin."""
    return "su:{}".format(chat_id)


async def _wizard_debounce(chat_id, ttl=5) -> bool:
    """True — birinchi marta (davom etish mumkin), False — juda tez qayta bosildi."""
    r = await get_redis()
    return bool(await r.set("tg_wizard_rl:{}".format(chat_id), "1", ex=ttl, nx=True))


def _is_assistant(u) -> bool:
    return str(u.role) == "assistant_teacher"


def _kb_for(u):
    """Rolga mos asosiy menyu."""
    return ASSISTANT_KB if _is_assistant(u) else MAIN_KB


def _appt_status(a):
    if a.is_confirm is True:
        return "✅ Tasdiqlangan"
    if a.is_confirm is False:
        return "❌ Bekor qilingan"
    return "⏳ Kutilmoqda"


async def _bookings_list(db, assistant_id):
    """Bugundan boshlab kelgusi yozuvlar (bekor qilinganlardan tashqari)."""
    since = local_now() - timedelta(hours=12)
    res = await db.execute(
        select(TeacherAppointment, User)
        .join(User, User.id == TeacherAppointment.student_id)
        .where(and_(TeacherAppointment.teacher_id == assistant_id,
                    TeacherAppointment.date >= since,
                    TeacherAppointment.is_confirm.isnot(False)))
        .order_by(TeacherAppointment.date)
    )
    return res.all()


def _bookings_kb(rows):
    kb = []
    for a, st in rows[:30]:
        mark = "✅" if a.is_confirm else "⏳"
        kb.append([{"text": "{} {} — {}".format(mark, fmt(a.date, "%d.%m %H:%M"),
                                                (st.full_name or "—")[:28]),
                    "callback_data": "ap:{}".format(a.id)}])
    kb.append([{"text": "⬅️ Yopish", "callback_data": "del"}])
    return {"inline_keyboard": kb}


async def _send_bookings(db, chat_id, assistant_id, msg_id=None):
    rows = await _bookings_list(db, assistant_id)
    if not rows:
        txt = "📌 <b>Yozuvlar</b>\n\nHozircha kelgusi yozuv yo'q."
        kb = {"inline_keyboard": [[{"text": "⬅️ Yopish", "callback_data": "del"}]]}
    else:
        txt = "📌 <b>Yozuvlar</b> ({} ta)\n\nBatafsil ko'rish uchun bosing:".format(len(rows))
        kb = _bookings_kb(rows)
    if msg_id:
        await tb_edit(chat_id, msg_id, txt, kb)
    else:
        await tb_send(chat_id, txt, kb)


async def _dayoff_kb(db, assistant_id):
    """Kelgusi 14 kun — belgilanganlari 🚫 bilan."""
    today = local_now().date()
    res = await db.execute(select(AssistantDayOff.date).where(and_(
        AssistantDayOff.assistant_id == assistant_id,
        AssistantDayOff.date >= today)))
    off = {d for d in res.scalars().all()}
    rows, cur = [], []
    for i in range(14):
        d = today + timedelta(days=i)
        label = "{} {}".format(d.strftime("%d.%m"), UZ_DAYS[d.weekday()][:3])
        if d in off:
            label = "🚫 " + label
        cur.append({"text": label, "callback_data": "off:{}".format(d.isoformat())})
        if len(cur) == 2:
            rows.append(cur); cur = []
    if cur:
        rows.append(cur)
    rows.append([{"text": "⬅️ Yopish", "callback_data": "del"}])
    return {"inline_keyboard": rows}, len(off)


DAYOFF_TEXT = ("🚫 <b>Dam olish kunlari</b>\n\n"
               "Ishga kelolmaydigan kuningizni bosib belgilang. "
               "Belgilangan kunga o'quvchilar yozila olmaydi.\n"
               "Bekor qilish uchun o'sha kunni qayta bosing.")



# ── Guruhga havola orqali o'quvchi ro'yxatdan o'tishi ──────────────────────────
#
# Admin guruh sahifasida "Havola" tugmasini bosadi -> backend
# https://t.me/<bot>?start=<token> havolasini beradi (Group.invite_token).
# O'quvchi shu havolani bossa, Telegram botni "/start <token>" xabari bilan
# ochadi. Quyidagi wizard hamma narsani shu bitta oqim ichida boshqaradi va
# ustozlarga oid hech qanday holatga (contact-gate, menyu tugmalari) tegmaydi
# — buning uchun xabar ishlov berishning ENG boshida ushbu wizard holati
# tekshiriladi va agar faol bo'lsa, boshqa hech narsaga qaramay shu yerga
# yo'naltiriladi.

ROLE_LABELS_UZ = {
    "teacher": "o'qituvchi", "assistant_teacher": "yordamchi ustoz",
    "admin": "administrator", "superadmin": "administrator",
    "manager": "menejer", "cashier": "kassir", "staff": "xodim",
}

STUDENT_REG_PROMPTS = {
    "familiya": "Familiyangiz?",
    "otasi": "Otangizning ismi?",
    "parent_phone": "Ota-onangizning telefon raqami? (masalan: +998901234567)",
    "birth": "Tug'ilgan sanangiz? (kun.oy.yil, masalan: 14.05.2010)",
}


def _valid_name(text):
    """Ism/familiya/otasining ismi uchun yengil tekshiruv."""
    v = (text or "").strip()
    if not (2 <= len(v) <= 60):
        return None
    if v.startswith("/"):
        return None
    if any(ch.isdigit() for ch in v):
        return None
    return v


def _parse_birth(text):
    v = (text or "").strip()
    m = re.match(r"^(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})$", v)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m2 = re.match(r"^(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})$", v)
        if not m2:
            return None
        y, mo, d = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
    try:
        dt = date_cls(y, mo, d)
    except ValueError:
        return None
    if dt > date_cls.today() or dt.year < 1950:
        return None
    return dt


def _normalize_parent_phone(text):
    digits = re.sub(r"[^\d+]", "", text or "")
    if not digits:
        return None
    if not digits.startswith("+"):
        digits = "+" + digits.lstrip("+")
    if not re.match(r"^\+\d{9,15}$", digits):
        return None
    return digits


async def _group_by_token(db: AsyncSession, token: str):
    if not token or len(token) > 32:
        return None
    # "planned" — guruh hali boshlanmagan, lekin aynan shu bosqichda o'quvchi
    # yig'ish uchun havola ko'pincha ishlatiladi. "completed"/"stopped"
    # guruhlarga esa yangi yozilish mantiqsiz.
    res = await db.execute(select(Group).where(
        Group.invite_token == token, Group.status.in_(("active", "planned"))))
    group = res.scalars().first()
    if not group:
        return None
    if group.invite_token_expires_at and group.invite_token_expires_at <= local_now_utc():
        return None
    return group


def local_now_utc():
    from datetime import timezone
    return datetime.now(timezone.utc)


async def _add_to_group(db: AsyncSession, group, user) -> bool:
    """Yangi qo'shilsa True, allaqachon a'zo bo'lsa False qaytaradi.

    ON CONFLICT DO NOTHING ishlatiladi — webhook qayta yetkazilishi yoki
    parallel workerlar bir vaqtda ishlaganda ham xato bermay, xavfsiz
    ishlaydi (group_students (group_id, student_id) ustida UNIQUE bor).
    """
    stmt = pg_insert(GroupStudent).values(
        group_id=group.id, student_id=user.id
    ).on_conflict_do_nothing(index_elements=["group_id", "student_id"])
    result = await db.execute(stmt)
    return result.rowcount > 0


async def _bind_chat(db: AsyncSession, chat_id, user):
    """Bitta Telegram akkaunt = bitta foydalanuvchi (boshqa userdan uzib bog'laydi).

    users.telegram_id ustida qisman UNIQUE indeks bor — parallel so'rov bir xil
    chatni ikki xil userga bog'lamoqchi bo'lsa, kech qolgani shu yerda muvaffaqiyatsiz
    tugaydi (boshqasi allaqachon g'olib chiqqan bo'ladi, natija baribir to'g'ri).
    """
    await db.execute(
        sa_update(User).where(and_(User.telegram_id == str(chat_id), User.id != user.id))
        .values(telegram_id=None))
    user.telegram_id = str(chat_id)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise


async def _finish_student_registration(db: AsyncSession, chat_id, wait):
    token = wait.get("token")
    data = wait.get("data") or {}
    # Wizard holatini DARHOL tozalaymiz (DB ishlaridan oldin) — Telegram
    # webhookni qayta yetkazsa yoki bir vaqtda ikkita worker ushbu xabarni
    # qayta ishlasa, takroriy so'rov bu yerga qaytadan kirmaydi va shu bilan
    # ikki marta hisob yaratish xavfi keskin kamayadi.
    await clear_wait(_su_key(chat_id))

    group = await _group_by_token(db, token)
    if not group:
        await tb_send(chat_id, "❌ Havola muddati o'tgan yoki guruh faol emas. "
                               "Ustozdan yangi havola so'rang.")
        return

    phone = data.get("phone", "")
    res = await db.execute(select(User).where(User.phone == phone))
    existing = res.scalars().first()

    if existing:
        # Xavfsizlik: shu raqam bilan hisob TOPILGANI bilan avtomatik bog'lab
        # yubormaymiz — telefon raqami vaqt o'tib boshqa odamga tegishli bo'lib
        # qolgan bo'lishi mumkin (raqam qayta berilishi). O'quvchidan aniq
        # tasdiq so'raymiz, faqat "Ha" desa bog'laymiz.
        if str(existing.role) != "student":
            await tb_send(chat_id,
                          "❌ Bu telefon raqami bilan boshqa turdagi hisob mavjud. "
                          "Administratorga murojaat qiling.")
            return
        await set_wait(_su_key(chat_id), {
            "flow": "student_reg_confirm",
            "token": token,
            "existing_user_id": str(existing.id),
        })
        kb = {"inline_keyboard": [[
            {"text": "✅ Ha, bu men", "callback_data": "sic:yes"},
            {"text": "❌ Yo'q", "callback_data": "sic:no"},
        ]]}
        await tb_send(chat_id,
                      "🔎 Tizimda <b>{}</b> nomli hisob shu telefon raqami bilan "
                      "allaqachon mavjud.\n\nBu sizmisiz?".format(existing.full_name), kb)
        return

    password = (data.get("ism", "x")[:1] or "x").lower() + "00000000"
    user = User(
        full_name="{} {}".format(data.get("ism", ""), data.get("familiya", "")).strip(),
        phone=phone,
        password_hash=hash_password(password),
        role="student",
        is_active=True,
        student_status="active",
        must_change_password=True,
        father_name=data.get("otasi"),
        father_phone=data.get("parent_phone"),
        birth_date=data.get("birth"),
        branch_id=group.branch_id,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        # Poyga holati: shu oraliqda boshqa so'rov bir xil raqamni yaratib ulgurdi.
        await db.rollback()
        res2 = await db.execute(select(User).where(User.phone == phone))
        existing2 = res2.scalars().first()
        if not existing2 or str(existing2.role) != "student":
            await tb_send(chat_id,
                          "❌ Bu telefon raqami bilan hisob allaqachon mavjud. "
                          "Administratorga murojaat qiling.")
            return
        # Boshqa so'rov allaqachon shu raqamni yaratib ulgurgan — sizmisiz deb so'raymiz.
        await set_wait(_su_key(chat_id), {
            "flow": "student_reg_confirm", "token": token,
            "existing_user_id": str(existing2.id),
        })
        kb = {"inline_keyboard": [[
            {"text": "✅ Ha, bu men", "callback_data": "sic:yes"},
            {"text": "❌ Yo'q", "callback_data": "sic:no"},
        ]]}
        await tb_send(chat_id,
                      "🔎 Tizimda <b>{}</b> nomli hisob shu telefon raqami bilan "
                      "allaqachon mavjud.\n\nBu sizmisiz?".format(existing2.full_name), kb)
        return

    try:
        await _bind_chat(db, chat_id, user)
    except IntegrityError:
        await tb_send(chat_id, "❌ Xatolik yuz berdi. Havolani qaytadan bosing.")
        return
    added = await _add_to_group(db, group, user)
    await db.commit()

    lines_out = ["✅ <b>{}</b> guruhiga {}!".format(
        group.name, "qo'shildingiz" if added else "allaqachon a'zosiz"),
        "",
        "📱 <b>Tizimga kirish uchun:</b>",
        "Login: <code>{}</code>".format(phone),
        "Parol: <code>{}</code>".format(password),
        "",
        "⚠️ Xavfsizlik uchun birinchi kirishda parolni Profil bo'limidan "
        "o'zgartirishni tavsiya qilamiz."]
    if group.group_link:
        lines_out += ["", "🔗 <b>Guruh Telegram chatiga qo'shilish uchun:</b>", group.group_link]
    await tb_send(chat_id, "\n".join(lines_out))





async def _handle_student_reg(db: AsyncSession, chat_id, text, contact, sender_id, wait):
    step = wait.get("step")
    data = wait.get("data") or {}

    if text and text.strip().lower() in ("/cancel", "bekor", "bekor qilish"):
        await clear_wait(_su_key(chat_id))
        await tb_send(chat_id, "Ro'yxatdan o'tish bekor qilindi. Havolani qaytadan bosishingiz mumkin.")
        return {"ok": True}

    if step == "ism":
        v = _valid_name(text)
        if not v:
            await tb_send(chat_id, "Ismingizni to'g'ri kiriting (kamida 2 ta harf).")
            return {"ok": True}
        data["ism"] = v
        wait["step"], wait["data"] = "familiya", data
        await set_wait(_su_key(chat_id), wait)
        await tb_send(chat_id, STUDENT_REG_PROMPTS["familiya"])
        return {"ok": True}

    if step == "familiya":
        v = _valid_name(text)
        if not v:
            await tb_send(chat_id, "Familiyangizni to'g'ri kiriting.")
            return {"ok": True}
        data["familiya"] = v
        wait["step"], wait["data"] = "otasi", data
        await set_wait(_su_key(chat_id), wait)
        await tb_send(chat_id, STUDENT_REG_PROMPTS["otasi"])
        return {"ok": True}

    if step == "otasi":
        v = _valid_name(text)
        if not v:
            await tb_send(chat_id, "To'g'ri kiriting.")
            return {"ok": True}
        data["otasi"] = v
        wait["step"], wait["data"] = "phone", data
        await set_wait(_su_key(chat_id), wait)
        await tb_send(chat_id, "Telefon raqamingizni pastdagi tugma orqali yuboring 👇", PHONE_KB)
        return {"ok": True}

    if step == "phone":
        if not contact:
            await tb_send(chat_id,
                          "Iltimos, pastdagi <b>tugma</b> orqali telefon raqamingizni yuboring.",
                          PHONE_KB)
            return {"ok": True}
        if not contact.get("user_id") or contact.get("user_id") != sender_id:
            await tb_send(chat_id, "❌ Faqat o'zingizning kontaktingizni yuboring.", PHONE_KB)
            return {"ok": True}
        phone = contact.get("phone_number", "")
        if phone and not phone.startswith("+"):
            phone = "+" + phone
        data["phone"] = phone
        wait["step"], wait["data"] = "parent_phone", data
        await set_wait(_su_key(chat_id), wait)
        await tb_send(chat_id, STUDENT_REG_PROMPTS["parent_phone"], {"remove_keyboard": True})
        return {"ok": True}

    if step == "parent_phone":
        v = _normalize_parent_phone(text)
        if not v:
            await tb_send(chat_id, "Telefon raqamni to'g'ri kiriting (masalan: +998901234567).")
            return {"ok": True}
        data["parent_phone"] = v
        wait["step"], wait["data"] = "birth", data
        await set_wait(_su_key(chat_id), wait)
        await tb_send(chat_id, STUDENT_REG_PROMPTS["birth"])
        return {"ok": True}

    if step == "birth":
        v = _parse_birth(text)
        if not v:
            await tb_send(chat_id, "Sanani to'g'ri kiriting. Masalan: 14.05.2010")
            return {"ok": True}
        data["birth"] = v
        wait["data"] = data
        await _finish_student_registration(db, chat_id, wait)
        return {"ok": True}

    await clear_wait(_su_key(chat_id))
    await tb_send(chat_id, "Xatolik yuz berdi. Havolani qaytadan bosing.")
    return {"ok": True}


async def _start_with_token(db: AsyncSession, chat_id, token, teacher):
    group = await _group_by_token(db, token)
    if not group:
        if teacher:
            await tb_send(chat_id, "Xush kelibsiz, <b>{}</b>!".format(teacher.full_name), _kb_for(teacher))
        else:
            await tb_send(chat_id,
                          "Havola noto'g'ri yoki muddati o'tgan.\n\n"
                          "Tizimga kirish uchun telefon raqamingizni yuboring.",
                          PHONE_KB)
        return {"ok": True}

    existing_user = await _user_by_chat(db, chat_id)
    if existing_user:
        if str(existing_user.role) != "student":
            label = ROLE_LABELS_UZ.get(str(existing_user.role), str(existing_user.role))
            await tb_send(chat_id,
                          "❌ Bu havola faqat o'quvchilar uchun. "
                          "Sizning hisobingiz — {}.".format(label))
            return {"ok": True}
        added = await _add_to_group(db, group, existing_user)
        await db.commit()
        lines = ["✅ <b>{}</b> guruhiga {}!".format(
            group.name, "qo'shildingiz" if added else "allaqachon a'zosiz")]
        if group.group_link:
            lines += ["", "🔗 Guruh Telegram chatiga qo'shilish uchun:", group.group_link]
        await tb_send(chat_id, "\n".join(lines))
        return {"ok": True}

    if not await _wizard_debounce(chat_id):
        # Telegram ba'zan bir bosishni tez orada ikki marta yetkazadi —
        # shu holatda ikkinchi xabarni jimgina e'tiborsiz qoldiramiz.
        return {"ok": True}

    await set_wait(_su_key(chat_id), {"flow": "student_reg", "step": "ism", "token": token, "data": {}})
    await tb_send(chat_id,
                  "👋 Assalomu alaykum!\n\n<b>{}</b> guruhiga yozilish uchun "
                  "ma'lumotlaringizni to'ldiramiz.\n\nIsmingiz?".format(group.name),
                  {"remove_keyboard": True})
    return {"ok": True}


async def _handle_student_confirm_callback(db: AsyncSession, chat_id, msg_id, cb_id, data):
    """'Bu sizmisiz?' tugmasiga javob — mavjud hisobni shu chatga bog'lash tasdig'i."""
    wait = await get_wait(_su_key(chat_id))
    if not wait or wait.get("flow") != "student_reg_confirm":
        await tb_answer(cb_id, "Bu so'rov eskirgan. Havolani qaytadan bosing.", True)
        return {"ok": True}

    # Bir martalik — tugmani ikki marta bossa ikkinchisi hech narsa qilmaydi.
    await clear_wait(_su_key(chat_id))
    answer = data.split(":", 1)[1] if ":" in data else ""

    if answer != "yes":
        await tb_edit(chat_id, msg_id,
                      "Tushunarli. Agar bu hisob aslida sizga tegishli bo'lsa, "
                      "administratorga murojaat qiling.")
        await tb_answer(cb_id)
        return {"ok": True}

    group = await _group_by_token(db, wait.get("token"))
    res = await db.execute(select(User).where(User.id == uuid_mod.UUID(wait.get("existing_user_id", ""))))
    user = res.scalar_one_or_none()
    if not group or not user:
        await tb_edit(chat_id, msg_id, "❌ Havola muddati o'tgan. Qaytadan urinib ko'ring.")
        await tb_answer(cb_id)
        return {"ok": True}

    try:
        await _bind_chat(db, chat_id, user)
    except IntegrityError:
        await tb_answer(cb_id, "Xatolik yuz berdi, qaytadan urining.", True)
        return {"ok": True}
    added = await _add_to_group(db, group, user)
    await db.commit()

    lines = ["✅ <b>{}</b> guruhiga {}!".format(
        group.name, "qo'shildingiz" if added else "allaqachon a'zosiz")]
    if group.group_link:
        lines += ["", "🔗 Guruh Telegram chatiga qo'shilish uchun:", group.group_link]
    await tb_edit(chat_id, msg_id, "\n".join(lines))
    await tb_answer(cb_id, "✅ Tasdiqlandi", True)
    return {"ok": True}

@router.post("/webhook")

async def teacher_bot_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        update = await request.json()
    except Exception:
        return {"ok": True}

    # ── Callback (tugmalar) ──────────────────────────────────────────────
    cq = update.get("callback_query")
    if cq:
        data = cq.get("data") or ""
        chat_id = cq["message"]["chat"]["id"]
        msg_id = cq["message"]["message_id"]
        cb_id = cq["id"]

        # Student-registration "Bu sizmisiz?" tugmasi — chat hali hech qanday
        # hisobga bog'lanmagan bo'lishi mumkin, shuning uchun pastdagi
        # ustozga-oid gate'dan OLDIN alohida ishlov beriladi.
        if data.startswith("sic:"):
            return await _handle_student_confirm_callback(db, chat_id, msg_id, cb_id, data)

        teacher = await _teacher_by_chat(db, chat_id)
        if not teacher:
            await tb_answer(cb_id, "Ruxsat yo'q", True)
            return {"ok": True}

        if data == "del":
            await tb_delete(chat_id, msg_id)
            await tb_answer(cb_id)
            return {"ok": True}


        # ── Uy vazifa bahosini ustoz o'zgartirishi ───────────────────────
        if data.startswith("hg:"):
            _, sub_id, val = data.split(":")
            res = await db.execute(
                select(LessonHomeworkSubmission)
                .where(LessonHomeworkSubmission.id == uuid_mod.UUID(sub_id)))
            sub = res.scalar_one_or_none()
            if not sub:
                await tb_answer(cb_id, "Topshiriq topilmadi", True)
                return {"ok": True}
            hwres = await db.execute(
                select(LessonHomework).where(LessonHomework.id == sub.homework_id))
            hw = hwres.scalar_one_or_none()
            # Faqat shu o'quvchining ustozi baholay oladi
            owner = await hw_grader.teacher_for_student(db, sub.student_id, hw.lesson_id) if hw else None
            if not owner or owner.id != teacher.id:
                await tb_answer(cb_id, "Ruxsat yo'q", True)
                return {"ok": True}
            score = max(0, min(5, int(val)))
            sub.score = score
            sub.status = SubmissionStatus.graded
            sub.graded_by = teacher.id
            sub.graded_at = local_now()
            await db.commit()
            stres = await db.execute(select(User).where(User.id == sub.student_id))
            student = stres.scalar_one_or_none()
            try:
                await notify_user(db, sub.student_id, "Uy vazifa bahosi yangilandi",
                                  "{} — ustoz bahosi: {}/5".format(
                                      hw.title if hw else "Uy vazifa", score),
                                  notification_type="homework")
                await db.commit()
            except Exception:
                pass
            ai_line = ("🤖 AI bahosi edi: {}/5\n".format(sub.ai_score)
                       if sub.ai_score is not None else "")
            await tb_edit(chat_id, msg_id,
                          "✅ <b>Baho saqlandi</b>\n\n"
                          "👤 {}\n📌 {}\n\n{}"
                          "👨‍🏫 Sizning bahoyingiz: <b>{}/5</b>".format(
                              (student.full_name if student else "—"),
                              (hw.title if hw else "—"), ai_line, score))
            await tb_answer(cb_id, "✅ Baho: {}/5".format(score), True)
            return {"ok": True}

        # ── Yordamchi ustoz: yozuvlar ────────────────────────────────────
        if data == "bk":
            await _send_bookings(db, chat_id, teacher.id, msg_id)
            await tb_answer(cb_id)
            return {"ok": True}

        if data.startswith("ap:"):
            res = await db.execute(
                select(TeacherAppointment, User)
                .join(User, User.id == TeacherAppointment.student_id)
                .where(TeacherAppointment.id == uuid_mod.UUID(data[3:])))
            row = res.first()
            if not row or row[0].teacher_id != teacher.id:
                await tb_answer(cb_id, "Yozuv topilmadi", True)
                return {"ok": True}
            a, st = row
            lines = [
                "📌 <b>Yozuv</b>",
                "",
                "👤 O'quvchi: <b>{}</b>".format(st.full_name or "—"),
                "📞 {}".format(st.phone or "—"),
                "📅 {} ({})".format(fmt(a.date), UZ_DAYS[to_local(a.date).weekday()]),
                "📊 Holat: {}".format(_appt_status(a)),
            ]
            if a.message:
                lines += ["", "💬 {}".format(a.message)]
            btns = []
            if a.is_confirm is not True:
                btns.append({"text": "✅ Tasdiqlash", "callback_data": "apok:{}".format(a.id)})
            btns.append({"text": "❌ Bekor qilish", "callback_data": "apno:{}".format(a.id)})
            kb = {"inline_keyboard": [btns, [{"text": "⬅️ Ortga", "callback_data": "bk"}]]}
            await tb_edit(chat_id, msg_id, "\n".join(lines), kb)
            await tb_answer(cb_id)
            return {"ok": True}

        if data.startswith("apok:"):
            res = await db.execute(select(TeacherAppointment).where(
                TeacherAppointment.id == uuid_mod.UUID(data[5:])))
            a = res.scalar_one_or_none()
            if not a or a.teacher_id != teacher.id:
                await tb_answer(cb_id, "Yozuv topilmadi", True)
                return {"ok": True}
            a.is_confirm = True
            a.cancel_reason = None
            await db.commit()
            when_s = fmt(a.date)
            await notify_user(db, a.student_id, "Yozuvingiz tasdiqlandi",
                              "{} — {} sizni kutadi.".format(when_s, teacher.full_name),
                              notification_type="appointment")
            await db.commit()
            await tb_answer(cb_id, "✅ Tasdiqlandi", True)
            await _send_bookings(db, chat_id, teacher.id, msg_id)
            return {"ok": True}

        if data.startswith("apno:"):
            aid = data[5:]
            res = await db.execute(select(TeacherAppointment).where(
                TeacherAppointment.id == uuid_mod.UUID(aid)))
            a = res.scalar_one_or_none()
            if not a or a.teacher_id != teacher.id:
                await tb_answer(cb_id, "Yozuv topilmadi", True)
                return {"ok": True}
            await set_wait(chat_id, {"action": "cancel_reason", "appt_id": aid})
            await tb_edit(chat_id, msg_id,
                          "❌ <b>Bekor qilish</b>\n\n📅 {}\n\n"
                          "Bekor qilish <b>sababini</b> yozib yuboring 👇".format(
                              fmt(a.date)),
                          {"inline_keyboard": [[{"text": "⬅️ Ortga", "callback_data": "bk"}]]})
            await tb_answer(cb_id)
            return {"ok": True}

        # ── Yordamchi ustoz: dam olish kuni ──────────────────────────────
        if data.startswith("off:"):
            if not _is_assistant(teacher):
                await tb_answer(cb_id, "Ruxsat yo'q", True)
                return {"ok": True}
            d = date_cls.fromisoformat(data[4:])
            res = await db.execute(select(AssistantDayOff).where(and_(
                AssistantDayOff.assistant_id == teacher.id, AssistantDayOff.date == d)))
            ex = res.scalars().first()
            if ex:
                await db.execute(sa_delete(AssistantDayOff).where(
                    AssistantDayOff.id == ex.id))
                note = "{} — dam olish bekor qilindi".format(d.strftime("%d.%m"))
            else:
                db.add(AssistantDayOff(assistant_id=teacher.id, date=d,
                                       reason="Bot orqali belgilandi"))
                note = "🚫 {} — dam olish kuni".format(d.strftime("%d.%m"))
            await db.commit()
            kb, cnt = await _dayoff_kb(db, teacher.id)
            await tb_edit(chat_id, msg_id, DAYOFF_TEXT, kb)
            await tb_answer(cb_id, note, True)
            return {"ok": True}

        # ── O'quvchini guruhdan chiqarish ────────────────────────────────
        if data.startswith("rm:"):
            gid = data[3:]
            res = await db.execute(select(Group).where(Group.id == uuid_mod.UUID(gid)))
            g = res.scalar_one_or_none()
            if not g or g.teacher_id != teacher.id:
                await tb_answer(cb_id, "Guruh topilmadi", True)
                return {"ok": True}
            studs = await _group_students(db, g.id)
            if not studs:
                await tb_answer(cb_id, "Bu guruhda o'quvchi yo'q", True)
                return {"ok": True}
            items = [{"id": str(x.id), "name": x.full_name or "—", "marked": False}
                     for x in studs[:40]]
            sid = await create_session({"group_id": gid, "group_name": g.name,
                                        "students": items})
            await tb_edit(chat_id, msg_id, remove_text(g.name, items),
                          remove_keyboard(sid, items))
            await tb_answer(cb_id)
            return {"ok": True}

        if data.startswith("rs:"):
            _, sid, idx = data.split(":")
            sess = await get_session(sid)
            if not sess:
                await tb_answer(cb_id, "Sessiya eskirgan. Qaytadan oching.", True)
                return {"ok": True}
            i = int(idx)
            if 0 <= i < len(sess["students"]):
                st = sess["students"][i]
                st["marked"] = not st.get("marked")
                await save_session(sid, sess)
                await tb_edit(chat_id, msg_id,
                              remove_text(sess["group_name"], sess["students"]),
                              remove_keyboard(sid, sess["students"]))
                if st["marked"]:
                    await tb_answer(cb_id, "«{}» guruhdan chiqariladi.\nSaqlash tugmasini bosing.".format(st["name"]), True)
                else:
                    await tb_answer(cb_id, "«{}» — bekor qilindi.".format(st["name"]), True)
            else:
                await tb_answer(cb_id)
            return {"ok": True}

        if data.startswith("rsv:"):
            sid = data[4:]
            sess = await get_session(sid)
            if not sess:
                await tb_answer(cb_id, "Sessiya eskirgan. Qaytadan oching.", True)
                return {"ok": True}
            marked = [s for s in sess["students"] if s.get("marked")]
            if not marked:
                await tb_answer(cb_id, "Hech kim belgilanmagan.", True)
                return {"ok": True}
            gid = uuid_mod.UUID(sess["group_id"])
            # faqat o'z guruhidan chiqara oladi
            gres = await db.execute(select(Group).where(Group.id == gid))
            g = gres.scalar_one_or_none()
            if not g or g.teacher_id != teacher.id:
                await tb_answer(cb_id, "Ruxsat yo'q", True)
                return {"ok": True}
            for s in marked:
                await db.execute(sa_delete(GroupStudent).where(and_(
                    GroupStudent.group_id == gid,
                    GroupStudent.student_id == uuid_mod.UUID(s["id"]))))
            await db.commit()
            names = ", ".join(s["name"] for s in marked[:10])
            await tb_edit(chat_id, msg_id,
                          "✅ <b>{}</b> — {} ta o'quvchi guruhdan chiqarildi.\n\n{}".format(
                              sess["group_name"], len(marked), names))
            await tb_answer(cb_id, "✅ Saqlandi! {} ta o'quvchi chiqarildi.".format(len(marked)), True)
            return {"ok": True}

        if data.startswith("n:"):
            await tb_answer(cb_id)
            return {"ok": True}

        if data.startswith("grp:"):
            gid = data[4:]
            res = await db.execute(select(Group).where(Group.id == uuid_mod.UUID(gid)))
            g = res.scalar_one_or_none()
            if not g or g.teacher_id != teacher.id:
                await tb_answer(cb_id, "Guruh topilmadi", True)
                return {"ok": True}
            studs = await _group_students(db, g.id)
            days, st, en = parse_schedule(g.schedule)
            lines = ["👥 <b>{}</b>".format(g.name), "🕒 {}".format(g.schedule or "—"),
                     "👤 O'quvchilar: {}".format(len(studs))]
            if g.group_link:
                lines.append("🔗 {}".format(g.group_link))
            lines.append("")
            for i, s in enumerate(studs[:40], 1):
                lines.append("{}. {}".format(i, s.full_name))
            kb = {"inline_keyboard": [
                [{"text": "❌ O'quvchilarni guruhdan chiqarish",
                  "callback_data": "rm:{}".format(gid)}],
                [{"text": "⬅️ Ortga", "callback_data": "del"}],
            ]}
            await tb_edit(chat_id, msg_id, "\n".join(lines), kb)
            await tb_answer(cb_id)
            return {"ok": True}

        if (data.startswith("att:") or data.startswith("m:")
                or data.startswith("all:") or data.startswith("sv:")):
            await tb_answer(cb_id,
                            "Bot orqali davomat belgilash o'chirilgan. "
                            "Iltimos, platformadan belgilang.", True)
            return {"ok": True}

        await tb_answer(cb_id)
        return {"ok": True}

    # ── Oddiy xabar ──────────────────────────────────────────────────────
    msg = update.get("message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    if not chat_id:
        return {"ok": True}
    text = (msg.get("text") or "").strip()
    contact = msg.get("contact")
    sender_id = (msg.get("from") or {}).get("id")

    # Guruhga havola orqali ro'yxatdan o'tish wizard'i faol bo'lsa — hamma
    # narsadan oldin shu yerga yo'naltiramiz (ustozga oid hech qanday
    # tekshiruv/gate bu oqimga tegmasin, chunki yangi o'quvchida hali
    # umuman hisob yo'q bo'lishi mumkin).
    wait_early = await get_wait(_su_key(chat_id))
    if wait_early and wait_early.get("flow") == "student_reg":
        if text == "/start":
            # Qayta /start bosilsa — joriy savolni qaytadan ko'rsatamiz,
            # ustoz oqimiga tushib qolmasin.
            step = wait_early.get("step")
            if step == "ism":
                await tb_send(chat_id, "Ismingiz?")
            elif step == "phone":
                await tb_send(chat_id, "Telefon raqamingizni pastdagi tugma orqali yuboring 👇", PHONE_KB)
            else:
                await tb_send(chat_id, STUDENT_REG_PROMPTS.get(step, "Davom eting."))
            return {"ok": True}
        return await _handle_student_reg(db, chat_id, text, contact, sender_id, wait_early)

    # Telefon yuborildi -> ustozni bog'laymiz
    if contact:
        # Faqat O'ZINING kontakti bo'lishi kerak (boshqa odamnikini yubora olmasin).
        # O'z kontaktini ulashganda contact.user_id == yuboruvchining id si bo'ladi.
        sender_id = (msg.get("from") or {}).get("id")
        if not contact.get("user_id") or contact.get("user_id") != sender_id:
            await tb_send(chat_id,
                          "❌ Iltimos, <b>faqat o'zingizning</b> kontaktingizni yuboring "
                          "(pastdagi tugma orqali).", PHONE_KB)
            return {"ok": True}
        phone = contact.get("phone_number", "")
        if phone and not phone.startswith("+"):
            phone = "+" + phone
        res = await db.execute(select(User).where(User.phone == phone, User.is_active == True))  # noqa: E712
        u = res.scalars().first()
        if not u or str(u.role) not in ("teacher", "assistant_teacher"):
            # faqat ustozlarga xizmat qiladi
            await tb_send(chat_id, "❌ Bu bot faqat o'qituvchilar uchun.")
            return {"ok": True}
        # Bitta Telegram akkaunt = bitta foydalanuvchi.
        # Shu chat boshqa userga bog'langan bo'lsa, avval uzamiz (aks holda
        # bot kimligini noto'g'ri aniqlaydi).
        await db.execute(
            sa_update(User).where(and_(User.telegram_id == str(chat_id), User.id != u.id))
            .values(telegram_id=None))
        u.telegram_id = str(chat_id)
        await db.commit()
        await tb_send(chat_id, "✅ Xush kelibsiz, <b>{}</b>!\nQuyidagi menyudan foydalaning.".format(
            u.full_name), _kb_for(u))
        return {"ok": True}

    teacher = await _teacher_by_chat(db, chat_id)

    if text.startswith("/start"):
        parts = text.split(maxsplit=1)
        payload = parts[1].strip() if len(parts) > 1 else ""
        if payload:
            return await _start_with_token(db, chat_id, payload, teacher)
        if teacher:
            await tb_send(chat_id, "Xush kelibsiz, <b>{}</b>!".format(teacher.full_name),
                          _kb_for(teacher))
        else:
            await tb_send(chat_id,
                          "Assalomu alaykum! Tizimga kirish uchun telefon raqamingizni yuboring.",
                          PHONE_KB)
        return {"ok": True}

    if not teacher:
        await tb_send(chat_id, "Telefon raqamingizni yuboring.", PHONE_KB)
        return {"ok": True}

    # ── Kutilayotgan matn: bekor qilish sababi ───────────────────────────
    wait = await get_wait(chat_id)
    if wait and wait.get("action") == "cancel_reason" and text and not text.startswith("/"):
        await clear_wait(chat_id)
        res = await db.execute(select(TeacherAppointment).where(
            TeacherAppointment.id == uuid_mod.UUID(wait["appt_id"])))
        a = res.scalar_one_or_none()
        if not a or a.teacher_id != teacher.id:
            await tb_send(chat_id, "Yozuv topilmadi.", _kb_for(teacher))
            return {"ok": True}
        a.is_confirm = False
        a.cancel_reason = text[:500]
        await db.commit()
        when_s = fmt(a.date)
        await notify_user(db, a.student_id, "Yozuvingiz bekor qilindi",
                          "{} — sabab: {}".format(when_s, text[:300]),
                          notification_type="appointment")
        await db.commit()
        await tb_send(chat_id,
                      "❌ <b>Bekor qilindi</b>\n\n📅 {}\n💬 Sabab: {}\n\n"
                      "O'quvchiga xabar yuborildi.".format(when_s, text[:300]),
                      _kb_for(teacher))
        return {"ok": True}

    if text == BTN_BOOKINGS:
        await _send_bookings(db, chat_id, teacher.id)
        return {"ok": True}

    if text == BTN_DAYOFF:
        if not _is_assistant(teacher):
            await tb_send(chat_id, "Bu bo'lim yordamchi ustozlar uchun.", _kb_for(teacher))
            return {"ok": True}
        kb, cnt = await _dayoff_kb(db, teacher.id)
        await tb_send(chat_id, DAYOFF_TEXT, kb)
        return {"ok": True}

    if text == BTN_TODAY:
        groups = await _teacher_groups(db, teacher.id)
        today = date_cls.today()
        wd = today.weekday()
        lines = ["📅 <b>Bugungi darslar</b> ({})\n".format(UZ_DAYS[wd])]
        found = 0
        for g in groups:
            days, st, en = parse_schedule(g.schedule)
            if wd in days:
                found += 1
                att = await db.execute(select(Attendance).where(and_(
                    Attendance.group_id == g.id, Attendance.date == today)))
                rows = att.scalars().all()
                marked = any(str(a.status.value if hasattr(a.status, "value") else a.status)
                             != "absent" for a in rows)
                lines.append("• <b>{}</b> — {}  {}".format(
                    g.name, g.schedule or "—", "✅ davomat bor" if marked else "⚠️ davomat yo'q"))
        if not found:
            lines.append("Bugun darsingiz yo'q. 🎉")
        await tb_send(chat_id, "\n".join(lines))
        return {"ok": True}

    if text == BTN_GROUPS:
        groups = await _teacher_groups(db, teacher.id)
        if not groups:
            await tb_send(chat_id, "Sizda aktiv guruh yo'q.")
            return {"ok": True}
        kb = {"inline_keyboard": [
            [{"text": g.name, "callback_data": "grp:{}".format(g.id)}] for g in groups[:40]
        ]}
        await tb_send(chat_id, "👥 <b>Guruhlaringiz</b> ({} ta):".format(len(groups)), kb)
        return {"ok": True}

    await tb_send(chat_id, "Menyudan tanlang 👇", _kb_for(teacher))
    return {"ok": True}
