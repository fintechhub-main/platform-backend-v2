import json
import secrets
import httpx
from fastapi import APIRouter, Header, HTTPException, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from app.database import get_db
from app.models.user import User, UserRole
from app.utils.auth import create_access_token, create_refresh_token
from app.schemas.user import UserOut
from app.config import settings
from app.redis_client import get_redis

TELEGRAM_BOT_TOKEN = settings.TELEGRAM_BOT_TOKEN
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
BOT_USERNAME = settings.TELEGRAM_BOT_USERNAME

# Redis key prefixes
_SESSION_KEY = "tg_session:{}"       # session_id -> session data (JSON), TTL 10 min
_CHAT_KEY    = "tg_chat:{}"          # chat_id    -> session_id,         TTL 10 min
_SESSION_TTL = 600                   # 10 daqiqa

router = APIRouter(tags=["telegram-auth"])


@router.post("/auth/telegram/init")
async def telegram_init():
    session_id = secrets.token_urlsafe(16)
    r = await get_redis()
    await r.set(_SESSION_KEY.format(session_id), json.dumps({"status": "pending"}), ex=_SESSION_TTL)
    bot_link = f"https://t.me/{BOT_USERNAME}?start={session_id}"
    return {"session_id": session_id, "bot_link": bot_link}


@router.get("/auth/telegram/status/{session_id}")
async def telegram_status(session_id: str):
    r = await get_redis()
    raw = await r.get(_SESSION_KEY.format(session_id))
    if not raw:
        raise HTTPException(status_code=404, detail="Session not found")
    session = json.loads(raw)
    # One-time fetch: remove after tokens delivered
    if session.get("status") == "completed":
        await r.delete(_SESSION_KEY.format(session_id))
    return session


@router.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    secret: Optional[str] = Header(None, alias="X-Telegram-Bot-Api-Secret-Token"),
):
    # H-2: webhook secret majburiy tekshiruv
    if not settings.TELEGRAM_WEBHOOK_SECRET or secret != settings.TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid webhook secret")
    try:
        data = await request.json()
    except Exception:
        return {"ok": True}

    message = data.get("message") or data.get("edited_message")
    if not message:
        return {"ok": True}

    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")
    contact = message.get("contact")
    r = await get_redis()

    if text and text.startswith("/start"):
        parts = text.split()
        session_id = parts[1] if len(parts) > 1 else None
        if session_id and await r.exists(_SESSION_KEY.format(session_id)):
            await r.set(_CHAT_KEY.format(chat_id), session_id, ex=_SESSION_TTL)
            await _send_phone_request(chat_id)
        else:
            await _send_message(
                chat_id,
                "Xush kelibsiz! Ilovadan Telegram orqali kirish tugmasini bosing.",
            )

    elif contact:
        phone = contact.get("phone_number", "")
        if not phone.startswith("+"):
            phone = "+" + phone

        session_id = await r.get(_CHAT_KEY.format(chat_id))
        if not session_id or not await r.exists(_SESSION_KEY.format(session_id)):
            await _send_message(chat_id, "Iltimos, ilovadan qayta urinib ko'ring.")
            return {"ok": True}

        result = await db.execute(
            select(User).where(User.phone == phone, User.is_active == True)
        )
        user = result.scalar_one_or_none()

        if not user:
            await r.set(_SESSION_KEY.format(session_id),
                        json.dumps({"status": "failed", "message": "Telefon raqam topilmadi"}),
                        ex=_SESSION_TTL)
            await _send_message(
                chat_id,
                f"❌ {phone} raqamli foydalanuvchi topilmadi.",
            )
        elif str(user.role) not in ("student", "teacher", "admin", "superadmin"):
            await r.set(_SESSION_KEY.format(session_id),
                        json.dumps({"status": "failed", "message": "Ruxsat yo'q"}),
                        ex=_SESSION_TTL)
            await _send_message(chat_id, "❌ Bu ilovaga kirish ruxsati yo'q.")
        else:
            # H-1: tv qo'shildi — parol o'zgarsa token bekor bo'ladi
            access_token = create_access_token(
                {"sub": str(user.id), "role": str(user.role), "tv": user.token_version}
            )
            refresh_token = create_refresh_token(
                {"sub": str(user.id), "tv": user.token_version}
            )
            payload = {
                "status": "completed",
                "access_token": access_token,
                "refresh_token": refresh_token,
                "user": UserOut.model_validate(user).model_dump(mode="json"),
            }
            await r.set(_SESSION_KEY.format(session_id), json.dumps(payload), ex=_SESSION_TTL)
            await _send_message(
                chat_id,
                f"✅ Xush kelibsiz, {user.full_name}! Ilovaga qaytishingiz mumkin.",
            )
            await r.delete(_CHAT_KEY.format(chat_id))

    return {"ok": True}


async def set_webhook(base_url: str) -> dict:
    url = f"{TELEGRAM_API}/setWebhook"
    webhook_url = f"{base_url}/api/v1/telegram/webhook"
    params = {"url": webhook_url}
    if settings.TELEGRAM_WEBHOOK_SECRET:
        params["secret_token"] = settings.TELEGRAM_WEBHOOK_SECRET
    async with httpx.AsyncClient() as client:
        r = await client.post(url, json=params)
        return r.json()


async def _send_message(chat_id: int, text: str):
    async with httpx.AsyncClient() as client:
        await client.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": text})


async def _send_phone_request(chat_id: int):
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{TELEGRAM_API}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": "Telefon raqamingizni ulashing:",
                "reply_markup": {
                    "keyboard": [[{"text": "📱 Telefon raqamni ulashish", "request_contact": True}]],
                    "resize_keyboard": True,
                    "one_time_keyboard": True,
                },
            },
        )
