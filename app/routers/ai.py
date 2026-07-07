import uuid
from datetime import date as today_date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.models.ai_settings import AISettings
from app.models.ai_usage import AIUsage
from app.services import ai_service

router = APIRouter(prefix="/ai", tags=["ai"])

# ─── Unlimited roles ──────────────────────────────────────────────────────────
UNLIMITED_ROLES = {"superadmin", "admin"}

DEFAULT_ROLE_LIMITS = {
    "student": 10,
    "teacher": 50,
    "assistant_teacher": 30,
    "manager": 50,
    "cashier": 20,
    "staff": 20,
    "default": 20,
}


def _get_limit_for_role(settings, role: str) -> int:
    role_limits = (getattr(settings, "role_limits", None) or {}) if settings else {}
    if role in role_limits and role_limits[role] is not None:
        return int(role_limits[role])
    if "default" in role_limits and role_limits["default"] is not None:
        return int(role_limits["default"])
    return DEFAULT_ROLE_LIMITS.get(role, DEFAULT_ROLE_LIMITS["default"])

# ─── Mode system prompts ──────────────────────────────────────────────────────
MODE_PROMPTS = {
    "ustoz": (
        "Siz ta'lim platformasining professional AI ustozisiz. O'zbek tilida aniq, qisqa va foydali javoblar bering. "
        "Tushuntirishlarni bosqichma-bosqich qiling. Misollar keltiring. Talabaning savoliga qarab murakkablik "
        "darajasini moslang. Rag'batlantiruvchi va iliq munosabatda bo'ling."
    ),
    "homework": (
        "Siz uy vazifalarni tekshiruvchi professional AI ustozisiz. Talaba uy vazifasini yoki javobini yuboradi. Siz:\n"
        "1. Javobdagi xatolarni aniq ko'rsating (qaysi qatorda, nima xato)\n"
        "2. To'g'ri javob yoki yechimni tushuntiring\n"
        "3. Bahoni 0–10 oralig'ida qo'ying va asoslang\n"
        "4. Qisqa, konstruktiv fikr-mulohaza bering\n"
        "O'zbek tilida javob bering. Qattiq emas, lekin aniq va halol bo'ling."
    ),
    "bugfix": (
        "Siz senior dasturchi va debugging ekspertisiz. Foydalanuvchi kod yoki xato xabari yuboradi. Siz:\n"
        "1. Xato sababini aniq va sodda tushuntiring\n"
        "2. Tuzatilgan kodni markdown kod blokida ko'rsating\n"
        "3. Nima noto'g'ri ekanini izohlab bering\n"
        "4. Yaxshilash yoki oldini olish maslahatlarini bering\n"
        "Tushuntirishlarni O'zbek tilida yozing, kod qismlarini o'zgartirishsiz qoldiring. "
        "Kodni doimo ```language ... ``` formatda ko'rsating."
    ),
    "interview": (
        "Siz texnik interyuv o'tkazuvchi senior dasturchi va HR ekspertisiz. Quyidagi qoidalarga amal qiling:\n"
        "1. Foydalanuvchi mavzu yoki pozitsiyani aytganida, 1 ta savol bering\n"
        "2. Javobni 1–10 baho bilan baholang va qisqa izoh bering\n"
        "3. Keyingi savolni bering (avvalgidan biroz qiyinroq)\n"
        "4. Har 5 savoldan keyin umumiy baho va tavsiya bering\n"
        "Savol turlari: nazariy, amaliy, kod yozish, vaziyat tahlili.\n"
        "Interyuvni real vaziyatdek olib boring. O'zbek tilida muloqot qiling."
    ),
    # ── Backward compat ──
    "general":  "Siz ta'lim platformasining AI ustozisiz. O'zbek tilida qisqa, aniq va foydali javoblar bering.",
    "math":     "Siz matematika ustozisiz (algebra, geometriya, calculus). Har bir qadamni tushuntiring. O'zbek tilida javob bering.",
    "code":     "Siz dasturlash ustozisiz (Python, JavaScript, algoritmlar). Kod misollar bilan tushuntiring. O'zbek tilida javob bering.",
    "english":  "You are an English language teacher. Help with grammar, vocabulary and speaking. Mix Uzbek explanations with English examples.",
    "science":  "Siz fan ustozisiz (fizika, kimyo, biologiya). Formulalar va misollar bilan tushuntiring. O'zbek tilida javob bering.",
    "history":  "Siz tarix ustozisiz. O'zbekiston va jahon tarixi bo'yicha aniq, qiziqarli javoblar bering. O'zbek tilida javob bering.",
}


# ─── Helpers ──────────────────────────────────────────────────────────────────
async def _get_or_create_usage(db: AsyncSession, user_id: uuid.UUID) -> AIUsage:
    today = today_date.today()
    row = (await db.execute(
        select(AIUsage).where(AIUsage.user_id == user_id, AIUsage.date == today)
    )).scalar_one_or_none()
    if not row:
        row = AIUsage(user_id=user_id, date=today, requests_count=0)
        db.add(row)
        await db.flush()
    return row


# ─── Schemas ──────────────────────────────────────────────────────────────────
class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    mode: Optional[str] = "ustoz"
    persona: Optional[str] = None  # backward compat alias


class SettingsUpdate(BaseModel):
    provider: Optional[str] = None
    openai_api_key: Optional[str] = None
    openai_model: Optional[str] = None
    gemini_api_key: Optional[str] = None
    gemini_model: Optional[str] = None
    claude_api_key: Optional[str] = None
    claude_model: Optional[str] = None
    deepseek_api_key: Optional[str] = None
    deepseek_model: Optional[str] = None
    token_budget: Optional[int] = None
    daily_limit: Optional[int] = None
    role_limits: Optional[dict] = None
    enabled_modules: Optional[dict] = None
    system_prompt: Optional[str] = None


# ─── Endpoints ────────────────────────────────────────────────────────────────
@router.get("/usage")
async def get_ai_usage(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Foydalanuvchining bugungi AI foydalanish statistikasi."""
    is_unlimited = str(current_user.role) in UNLIMITED_ROLES
    settings = await ai_service.get_settings(db)
    daily_limit = _get_limit_for_role(settings, str(current_user.role))

    today = today_date.today()
    row = (await db.execute(
        select(AIUsage).where(AIUsage.user_id == current_user.id, AIUsage.date == today)
    )).scalar_one_or_none()
    used = row.requests_count if row else 0

    return {
        "used": used,
        "limit": daily_limit,
        "remaining": daily_limit - used if not is_unlimited else 9999,
        "is_unlimited": is_unlimited,
        "role": str(current_user.role),
        "date": today.isoformat(),
    }


@router.post("/chat")
async def ai_chat(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("ai-teacher", "create")),
):
    # Resolve mode (mode field takes priority, fall back to persona for compat)
    mode = body.mode or body.persona or "ustoz"

    # Daily limit check (skip for admins)
    is_unlimited = str(current_user.role) in UNLIMITED_ROLES
    if not is_unlimited:
        settings = await ai_service.get_settings(db)
        daily_limit = _get_limit_for_role(settings, str(current_user.role))
        usage = await _get_or_create_usage(db, current_user.id)
        if usage.requests_count >= daily_limit:
            raise HTTPException(
                status_code=429,
                detail=f"Kunlik AI limit ({daily_limit} ta so'rov) tugadi. Ertaga qayta urinib ko'ring."
            )

    system_prompt = MODE_PROMPTS.get(mode, MODE_PROMPTS["ustoz"])
    messages = [{"role": m.role, "content": m.content} for m in body.messages]
    reply = await ai_service.chat(db, messages, system_prompt)

    # Increment usage
    if not is_unlimited:
        usage.requests_count += 1
        await db.commit()

    return {"reply": reply}


@router.get("/settings")
async def get_ai_settings(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("ai-teacher", "view")),
):
    settings = await ai_service.get_settings(db)
    if not settings:
        settings = AISettings()
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return {
        "id": str(settings.id),
        "provider": settings.provider,
        "openai_api_key": "***" if settings.openai_api_key else None,
        "openai_model": settings.openai_model,
        "gemini_api_key": "***" if settings.gemini_api_key else None,
        "gemini_model": settings.gemini_model,
        "claude_api_key": "***" if settings.claude_api_key else None,
        "claude_model": settings.claude_model,
        "deepseek_api_key": "***" if settings.deepseek_api_key else None,
        "deepseek_model": settings.deepseek_model,
        "token_budget": settings.token_budget,
        "daily_limit": getattr(settings, "daily_limit", 20),
        "role_limits": getattr(settings, "role_limits", None) or DEFAULT_ROLE_LIMITS,
        "enabled_modules": settings.enabled_modules,
        "system_prompt": settings.system_prompt,
    }


@router.patch("/settings")
async def update_ai_settings(
    body: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("ai-teacher", "update")),
):
    settings = await ai_service.get_settings(db)
    if not settings:
        settings = AISettings()
        db.add(settings)

    data = body.model_dump(exclude_none=True)
    for key_field in ("openai_api_key", "gemini_api_key", "claude_api_key", "deepseek_api_key"):
        if data.get(key_field) == "***":
            data.pop(key_field)

    for k, v in data.items():
        if hasattr(settings, k):
            setattr(settings, k, v)

    await db.commit()
    await db.refresh(settings)
    return {"ok": True}
