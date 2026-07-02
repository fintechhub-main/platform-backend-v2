import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.models.ai_settings import AISettings
from app.services import ai_service

router = APIRouter(prefix="/ai", tags=["ai"])

PERSONA_PROMPTS = {
    "general": "Siz ta'lim platformasining AI ustozisiz. O'zbek tilida qisqa, aniq va foydali javoblar bering.",
    "math": "Siz matematika ustozisiz (algebra, geometriya, calculus). Har bir qadamni tushuntiring. O'zbek tilida javob bering.",
    "code": "Siz dasturlash ustozisiz (Python, JavaScript, algoritmlar). Kod misollar bilan tushuntiring. O'zbek tilida javob bering.",
    "english": "You are an English language teacher. Help students with grammar, vocabulary and speaking. Mix Uzbek explanations with English examples.",
    "science": "Siz fan ustozisiz (fizika, kimyo, biologiya). Formulalar va misollar bilan tushuntiring. O'zbek tilida javob bering.",
    "history": "Siz tarix ustozisiz. O'zbekiston va jahon tarixi bo'yicha aniq, qiziqarli javoblar bering. O'zbek tilida javob bering.",
}


class ChatMessage(BaseModel):
    role: str  # user | assistant
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    persona: Optional[str] = "general"


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
    enabled_modules: Optional[dict] = None
    system_prompt: Optional[str] = None


@router.post("/chat")
async def ai_chat(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("ai-teacher", "create")),
):
    system_prompt = PERSONA_PROMPTS.get(body.persona or "general", PERSONA_PROMPTS["general"])
    messages = [{"role": m.role, "content": m.content} for m in body.messages]
    reply = await ai_service.chat(db, messages, system_prompt)
    return {"reply": reply}


@router.get("/settings")
async def get_ai_settings(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("ai-teacher", "view")),
):
    settings = await ai_service.get_settings(db)
    if not settings:
        # create default
        settings = AISettings()
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    # Mask API keys: return only whether they are set
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
    # Don't overwrite key with "***" (masked value returned from GET)
    for key_field in ("openai_api_key", "gemini_api_key", "claude_api_key", "deepseek_api_key"):
        if data.get(key_field) == "***":
            data.pop(key_field)

    for k, v in data.items():
        setattr(settings, k, v)

    await db.commit()
    await db.refresh(settings)
    return {"ok": True}
