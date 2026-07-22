"""Admin uchun AI chat — tabiiy tilda so'ralgan savolni ma'lumotlar bazasidagi
haqiqiy ma'lumotga aylantiradi.

Xavfsizlik: AI hech qachon xom SQL yozmaydi. AI faqat qaysi TAYYOR funksiya
chaqirilishini va uning parametrlarini (JSON) tanlaydi — haqiqiy so'rovni
`app/services/ai_query_functions.py` dagi qattiq yozilgan, parametrlangan
funksiyalar bajaradi. Shu tufayl AI javobidagi hech qanday matn to'g'ridan-to'g'ri
SQL sifatida ishlamaydi.
"""
import json
import logging
import re
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_permission
from app.services import ai_service
from app.services import ai_query_functions as qf

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai-chat", tags=["ai-chat"])


class ChatMessage(BaseModel):
    role: str   # "user" | "assistant"
    text: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


ACTIONS_DOC = """
Mavjud amallar (action) va parametrlari:
1. "absent_students" — berilgan sanada kelmagan o'quvchilar ro'yxati.
   params: {"date": "YYYY-MM-DD", "group_name": "guruh nomi yoki qismi (ixtiyoriy)"}
2. "underperforming_students" — o'rtacha bahosi past (o'zlashtirmayotgan) o'quvchilar.
   params: {"group_name": "ixtiyoriy", "threshold": son (standart 5.0)}
3. "group_roster" — bitta guruhdagi o'quvchilar ro'yxati.
   params: {"group_name": "guruh nomi (majburiy)"}
4. "student_lookup" — ism bo'yicha o'quvchi qidirish, profil va so'nggi davomat/baho.
   params: {"name": "ism yoki familiya (majburiy)"}
5. "attendance_stats" — guruh(lar) bo'yicha davomat foizi statistikasi.
   params: {"group_name": "ixtiyoriy", "date_from": "YYYY-MM-DD ixtiyoriy", "date_to": "YYYY-MM-DD ixtiyoriy"}
6. "top_students" — eng yuqori o'rtacha bahoga ega o'quvchilar.
   params: {"group_name": "ixtiyoriy", "limit": son (standart 10)}
7. "general" — yuqoridagilarning hech biriga to'g'ri kelmaydigan, oddiy suhbat
   yoki tushuntirish talab qiladigan savol. Bu holda "reply" maydoniga to'g'ridan-
   to'g'ri o'zbek tilida javob yozing (boshqa hech narsa kerak emas).
"""

def build_system_prompt(today: str) -> str:
    return (
        "Siz o'quv markazi (LMS) uchun ma'lumotlar assistentisiz.\n"
        "Admin sizga tabiiy tilda savol beradi (masalan: \"kecha kelmagan o'quvchilarni "
        "ko'rsat\", \"Python backend guruhida o'zlashtirmayotganlar kim\", \"Ali ismli "
        "o'quvchini top\"). Sizning vazifangiz — savolni quyidagi TAYYOR amallardan biriga "
        "moslashtirish, xom ma'lumotlarga o'zingiz kira olmaysiz.\n\n"
        f"Bugungi sana: {today}. \"kecha\"=kechagi sana, \"bugun\"=bugungi sana, "
        "\"shu hafta\" kabi nisbiy vaqtlarni shu sanaga nisbatan hisoblang.\n\n"
        "Suhbat tarixidan foydalaning — agar admin oldingi xabarga ishora qilib "
        "(\"shu guruh bo'yicha\", \"unga qarab\" kabi) yozsa, kontekstni saqlang.\n\n"
        f"{ACTIONS_DOC}\n\n"
        "JAVOBINGIZ FAQAT JSON bo'lsin, boshqa hech qanday matn yozmang:\n"
        '{"action": "<amal_nomi>", "params": {...}, "reply": "<faqat \'general\' uchun>"}'
    )


def _extract_json(text: str):
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


ACTION_MAP = {
    "absent_students": lambda db, p: qf.absent_students(
        db, p.get("date") or str(date.today()), p.get("group_name")),
    "underperforming_students": lambda db, p: qf.underperforming_students(
        db, p.get("group_name"), float(p.get("threshold") or 5.0)),
    "group_roster": lambda db, p: qf.group_roster(db, p.get("group_name") or ""),
    "student_lookup": lambda db, p: qf.student_lookup(db, p.get("name") or ""),
    "attendance_stats": lambda db, p: qf.attendance_stats(
        db, p.get("group_name"), p.get("date_from"), p.get("date_to")),
    "top_students": lambda db, p: qf.top_students(
        db, p.get("group_name"), int(p.get("limit") or 10)),
}


@router.post("/message")
async def send_message(
    data: ChatRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("ai-chat", "view")),
):
    history_msgs = [{"role": ("user" if m.role == "user" else "assistant"), "content": m.text}
                    for m in data.history[-8:]]
    history_msgs.append({"role": "user", "content": data.message})

    system = build_system_prompt(date.today().isoformat())
    raw = await ai_service.chat(db, history_msgs, system_prompt=system)

    if raw and (raw.startswith("AI xatosi") or "AI sozlamalari topilmadi" in raw):
        return {"reply": raw, "table": None, "chart": None}

    parsed = _extract_json(raw)
    if not parsed or "action" not in parsed:
        # AI JSON qaytarmadi — xom javobni to'g'ridan-to'g'ri suhbat sifatida ko'rsatamiz
        return {"reply": raw or "Javob berib bo'lmadi, qaytadan urinib ko'ring.", "table": None, "chart": None}

    action = parsed.get("action")
    params = parsed.get("params") or {}

    if action == "general" or action not in ACTION_MAP:
        return {"reply": parsed.get("reply") or "Tushunmadim, boshqacha so'rab ko'ring.",
                "table": None, "chart": None}

    try:
        reply, table, chart = await ACTION_MAP[action](db, params)
    except Exception as e:                      # noqa: BLE001
        logger.warning("[ai-chat] amal xatosi (%s): %s", action, e)
        return {"reply": "So'rovni bajarishda xatolik yuz berdi. Boshqacha so'rab ko'ring.",
                "table": None, "chart": None}

    return {"reply": reply, "table": table, "chart": chart}
