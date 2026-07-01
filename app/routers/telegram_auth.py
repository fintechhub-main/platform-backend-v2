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

TELEGRAM_BOT_TOKEN = settings.TELEGRAM_BOT_TOKEN
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
BOT_USERNAME = settings.TELEGRAM_BOT_USERNAME

# In-memory session store: session_id -> {status, access_token?, refresh_token?, user?}
_sessions: dict = {}
# telegram_chat_id -> session_id
_chat_sessions: dict = {}

router = APIRouter(tags=["telegram-auth"])


@router.post("/auth/telegram/init")
async def telegram_init():
    session_id = secrets.token_urlsafe(16)
    _sessions[session_id] = {"status": "pending"}
    bot_link = f"https://t.me/{BOT_USERNAME}?start={session_id}"
    return {"session_id": session_id, "bot_link": bot_link}


@router.get("/auth/telegram/status/{session_id}")
async def telegram_status(session_id: str):
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    # One-time fetch: remove session after tokens are delivered to prevent token leakage
    if session.get("status") == "completed":
        _sessions.pop(session_id, None)
    return session


@router.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    secret: Optional[str] = Header(None, alias="X-Telegram-Bot-Api-Secret-Token"),
):
    if settings.TELEGRAM_WEBHOOK_SECRET and secret != settings.TELEGRAM_WEBHOOK_SECRET:
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

    if text and text.startswith("/start"):
        parts = text.split()
        session_id = parts[1] if len(parts) > 1 else None
        if session_id and session_id in _sessions:
            _chat_sessions[chat_id] = session_id
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

        session_id = _chat_sessions.get(chat_id)
        if not session_id or session_id not in _sessions:
            await _send_message(chat_id, "Iltimos, ilovadan qayta urinib ko'ring.")
            return {"ok": True}

        # Find user by phone — student role required
        result = await db.execute(
            select(User).where(User.phone == phone, User.is_active == True)
        )
        user = result.scalar_one_or_none()

        if not user:
            _sessions[session_id] = {"status": "failed", "message": "Telefon raqam topilmadi"}
            await _send_message(
                chat_id,
                f"❌ {phone} raqamli foydalanuvchi topilmadi. Iltimos, ro'yxatdan o'tgan raqamni ulashing.",
            )
        elif user.role not in (UserRole.student, UserRole.teacher, UserRole.admin):
            _sessions[session_id] = {"status": "failed", "message": "Ruxsat yo'q"}
            await _send_message(chat_id, "❌ Bu ilovaga kirish ruxsati yo'q.")
        else:
            access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
            refresh_token = create_refresh_token({"sub": str(user.id)})
            _sessions[session_id] = {
                "status": "completed",
                "access_token": access_token,
                "refresh_token": refresh_token,
                "user": UserOut.model_validate(user).model_dump(mode="json"),
            }
            await _send_message(
                chat_id,
                f"✅ Xush kelibsiz, {user.full_name}! Ilovaga qaytishingiz mumkin.",
            )
            _chat_sessions.pop(chat_id, None)

    return {"ok": True}


async def _send_message(chat_id: int, text: str):
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            await client.post(
                f"{TELEGRAM_API}/sendMessage",
                json={"chat_id": chat_id, "text": text},
            )
        except Exception:
            pass


async def _send_phone_request(chat_id: int):
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            await client.post(
                f"{TELEGRAM_API}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": "📱 Telefon raqamingizni ulashing:",
                    "reply_markup": {
                        "keyboard": [
                            [{"text": "📞 Telefon raqamni ulashish", "request_contact": True}]
                        ],
                        "resize_keyboard": True,
                        "one_time_keyboard": True,
                    },
                },
            )
        except Exception:
            pass


async def set_webhook(base_url: str):
    webhook_url = f"{base_url}/api/v1/telegram/webhook"
    payload: dict = {"url": webhook_url, "allowed_updates": ["message"]}
    if settings.TELEGRAM_WEBHOOK_SECRET:
        payload["secret_token"] = settings.TELEGRAM_WEBHOOK_SECRET
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.post(f"{TELEGRAM_API}/setWebhook", json=payload)
            return resp.json()
        except Exception as e:
            return {"error": str(e)}
