"""Uy vazifani AI orqali baholash (0–5) va ustozga Telegram xabar yuborish.

AI faqat taklif beradi: bahо `ai_score` ga yoziladi va shu zahoti `score` ga
ko'chiriladi, lekin ustoz bot yoki platforma orqali uni o'zgartira oladi.
AI ishlamasa — topshiriq "submitted" holatida qoladi, ustoz qo'lda baholaydi.
"""
import json
import logging
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.group import Group, GroupStudent
from app.models.lesson import Lesson, Module
from app.models.user import User
from app.services import ai_service
from app.services.teacher_bot import tb_send

logger = logging.getLogger(__name__)

MAX_SCORE = 5

SYSTEM_PROMPT = (
    "Sen tajribali dasturlash o'qituvchisisan. O'quvchining uy vazifasini "
    "0 dan 5 gacha baholaysan (5 — a'lo, 0 — bajarilmagan). "
    "Javobing FAQAT JSON bo'lsin, boshqa matn yozma. "
    'Format: {"score": <0-5 butun son>, "feedback": "<o\'zbek tilida 1-3 gap izoh>"}'
)


def _extract_json(text: str):
    """AI javobidan JSON blokni ajratib oladi (```json ... ``` ichida ham bo'lishi mumkin)."""
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


async def ai_grade(db: AsyncSession, hw, submission) -> tuple[int | None, str]:
    """-> (ball yoki None, izoh). None qaytsa — AI baholay olmadi."""
    answer_parts = []
    if submission.text_answer:
        answer_parts.append("Matnli javob:\n" + submission.text_answer[:4000])
    if submission.code_answer:
        answer_parts.append("Kod:\n" + submission.code_answer[:4000])
    if submission.github_url:
        answer_parts.append("GitHub: " + submission.github_url)
    if submission.file_url:
        # Rasm mazmunini o'qiy olmaymiz — buni izohda ochiq aytamiz
        answer_parts.append(
            "O'quvchi fayl (rasm/PDF) biriktirgan. Fayl mazmuni matnga aylantirilmagan, "
            "shuning uchun uni baholay olmaysan.")

    if not answer_parts:
        return None, "Javob bo'sh"

    # Faqat fayl yuborilgan bo'lsa AI ni baholashga majburlamaymiz
    if not (submission.text_answer or submission.code_answer or submission.github_url):
        return None, "Faqat fayl yuborilgan — ustoz ko'rib baholaydi"

    user_msg = (
        f"Uy vazifa: {hw.title}\n"
        f"Topshiriq matni: {(hw.description or '')[:3000]}\n\n"
        f"O'quvchining javobi:\n" + "\n\n".join(answer_parts)
    )

    try:
        raw = await ai_service.chat(db, [{"role": "user", "content": user_msg}],
                                    system_prompt=SYSTEM_PROMPT)
    except Exception as e:                       # noqa: BLE001
        logger.warning("AI baholash xatosi: %s", e)
        return None, "AI bilan bog'lanib bo'lmadi"

    if raw and (raw.startswith("AI xatosi") or "AI sozlamalari topilmadi" in raw):
        logger.warning("AI baholash: %s", raw)
        return None, raw

    parsed = _extract_json(raw)
    if not parsed or "score" not in parsed:
        logger.warning("AI javobini o'qib bo'lmadi: %s", (raw or "")[:200])
        return None, "AI javobi tushunarsiz"

    try:
        score = int(round(float(parsed["score"])))
    except (TypeError, ValueError):
        return None, "AI bahosi noto'g'ri"
    score = max(0, min(MAX_SCORE, score))
    feedback = str(parsed.get("feedback") or "").strip()[:2000] or "Izoh berilmadi"
    return score, feedback


async def teacher_for_student(db: AsyncSession, student_id, lesson_id):
    """O'quvchining shu darsga tegishli guruhidagi ustozini topadi."""
    course_id = (await db.execute(
        select(Module.course_id).join(Lesson, Lesson.module_id == Module.id)
        .where(Lesson.id == lesson_id)
    )).scalars().first()
    if not course_id:
        return None
    q = (select(Group).join(GroupStudent, GroupStudent.group_id == Group.id)
         .where(GroupStudent.student_id == student_id, Group.course_id == course_id))
    group = (await db.execute(q)).scalars().first()
    if not group or not group.teacher_id:
        return None
    return (await db.execute(select(User).where(User.id == group.teacher_id))).scalars().first()


def grade_keyboard(sub_id) -> dict:
    """Ustoz bahoni bir bosishda o'zgartira olishi uchun 0–5 tugmalari."""
    return {"inline_keyboard": [
        [{"text": str(i), "callback_data": f"hg:{sub_id}:{i}"} for i in range(0, MAX_SCORE + 1)],
        [{"text": "✅ AI bahosini qoldirish", "callback_data": "del"}],
    ]}


async def notify_teacher(db: AsyncSession, hw, submission, student, lesson_title: str):
    """Ustozga Telegram orqali AI bahosini yuboradi (tugmalar bilan)."""
    teacher = await teacher_for_student(db, submission.student_id, hw.lesson_id)
    if not teacher or not teacher.telegram_id:
        return False

    score_line = (f"🤖 AI bahosi: <b>{submission.ai_score}/{MAX_SCORE}</b>"
                  if submission.ai_score is not None
                  else "🤖 AI baholay olmadi — qo'lda baholang")
    parts = [
        "📝 <b>Yangi uy vazifa topshirildi</b>",
        "",
        f"👤 O'quvchi: <b>{student.full_name or '—'}</b>",
        f"📚 Dars: {lesson_title}",
        f"📌 Vazifa: {hw.title}",
        "",
        score_line,
    ]
    if submission.ai_feedback:
        parts += ["", f"💬 {submission.ai_feedback[:500]}"]
    if submission.text_answer:
        parts += ["", f"✍️ Javob: {submission.text_answer[:400]}"]
    if submission.file_url:
        parts += ["", "📎 Fayl biriktirilgan (platformada ko'ring)"]
    parts += ["", "Bahoni o'zgartirish uchun raqamni bosing 👇"]

    try:
        await tb_send(teacher.telegram_id, "\n".join(parts), grade_keyboard(submission.id))
        return True
    except Exception as e:                       # noqa: BLE001
        logger.warning("Ustozga xabar yuborilmadi: %s", e)
        return False
