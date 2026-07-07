import uuid
import random
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import get_current_user
from app.limiter import limiter
from app.models.user import User
from app.models.integration_settings import IntegrationSettings
from app.redis_client import get_redis
from app.schemas.user import LoginRequest, TokenResponse, RefreshRequest, UserOut, UserCreate
from app.utils.auth import verify_password, hash_password, create_access_token, create_refresh_token, decode_token

router = APIRouter(prefix="/auth", tags=["auth"])


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


@router.post("/register", response_model=UserOut, status_code=201)
@limiter.limit("3/hour")
async def register(request: Request, data: UserCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.phone == data.phone))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Phone already registered")
    # SECURITY: role is always forced to 'student' — clients cannot self-assign admin
    from app.models.user import UserRole
    user = User(
        full_name=data.full_name,
        phone=data.phone,
        email=data.email,
        password_hash=hash_password(data.password),
        role=UserRole.student,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(request: Request, data: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.phone == data.phone))
    user = result.scalar_one_or_none()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    access_token = create_access_token({"sub": str(user.id), "role": str(user.role), "tv": user.token_version})
    refresh_token = create_refresh_token({"sub": str(user.id), "tv": user.token_version})
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserOut.model_validate(user),
    )


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("30/minute")
async def refresh_token(request: Request, data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = decode_token(data.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    result = await db.execute(select(User).where(User.id == uuid.UUID(payload["sub"])))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")

    # H-3: refresh token parol o'zgarishidan oldin olingan bo'lsa rad etish
    token_tv = payload.get("tv")
    if token_tv is not None and token_tv != user.token_version:
        raise HTTPException(status_code=401, detail="Token bekor qilingan. Qayta kiring.")

    access_token = create_access_token({"sub": str(user.id), "role": str(user.role), "tv": user.token_version})
    new_refresh = create_refresh_token({"sub": str(user.id), "tv": user.token_version})
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        user=UserOut.model_validate(user),
    )


class ForgotPasswordRequest(BaseModel):
    phone: str


class ForgotPasswordVerify(BaseModel):
    phone: str
    code: str


class ForgotPasswordReset(BaseModel):
    phone: str
    code: str
    new_password: str


OTP_TTL = 300  # 5 minutes


async def _send_otp_sms_text(phone: str, message: str, db: AsyncSession) -> bool:
    """Send a text via Eskiz if configured. Returns True if sent."""
    result = await db.execute(
        select(IntegrationSettings).where(
            IntegrationSettings.key == "eskiz",
            IntegrationSettings.is_active == True,
        )
    )
    eskiz = result.scalar_one_or_none()
    if not eskiz or not eskiz.login or not eskiz.password:
        return False

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            login_resp = await client.post(
                "https://notify.eskiz.uz/api/auth/login",
                data={"email": eskiz.login, "password": eskiz.password},
            )
            token = login_resp.json().get("data", {}).get("token")
            if not token:
                return False

            clean_phone = phone.lstrip("+")
            await client.post(
                "https://notify.eskiz.uz/api/message/sms/send",
                headers={"Authorization": f"Bearer {token}"},
                data={"mobile_phone": clean_phone, "message": message, "from": "4546"},
            )
        return True
    except Exception:
        return False


async def _send_otp_sms(phone: str, code: str, db: AsyncSession) -> bool:
    msg = f"EduHub: Parolni tiklash kodi: {code}. Amal qilish muddati 5 daqiqa."
    return await _send_otp_sms_text(phone, msg, db)


@router.post("/forgot-password")
@limiter.limit("3/hour")
async def forgot_password(
    request: Request,
    data: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.phone == data.phone, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        # Don't reveal whether phone exists
        return {"ok": True, "message": "Agar raqam ro'yxatda bo'lsa, kod yuborildi"}

    code = str(random.randint(100000, 999999))
    redis = await get_redis()
    await redis.setex(f"otp:{data.phone}", OTP_TTL, code)

    sms_sent = await _send_otp_sms(data.phone, code, db)

    response = {"ok": True, "message": "Agar raqam ro'yxatda bo'lsa, kod yuborildi"}
    # In dev (SMS not configured) return code for testing
    if not sms_sent:
        response["code"] = code
    return response


@router.post("/forgot-password/verify")
@limiter.limit("10/minute")
async def forgot_password_verify(
    request: Request,
    data: ForgotPasswordVerify,
):
    redis = await get_redis()
    stored = await redis.get(f"otp:{data.phone}")
    if not stored or stored != data.code:
        raise HTTPException(400, "Kod noto'g'ri yoki muddati o'tgan")
    # Mark as verified (extend TTL for reset step)
    await redis.setex(f"otp_verified:{data.phone}", OTP_TTL, data.code)
    return {"ok": True, "message": "Kod tasdiqlandi"}


@router.post("/forgot-password/reset")
@limiter.limit("5/hour")
async def forgot_password_reset(
    request: Request,
    data: ForgotPasswordReset,
    db: AsyncSession = Depends(get_db),
):
    if len(data.new_password) < 8:
        raise HTTPException(400, "Parol kamida 8 ta belgi bo'lishi kerak")

    redis = await get_redis()
    stored = await redis.get(f"otp_verified:{data.phone}")
    if not stored or stored != data.code:
        raise HTTPException(400, "Tasdiqlash kodi noto'g'ri yoki muddati o'tgan")

    result = await db.execute(select(User).where(User.phone == data.phone, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Foydalanuvchi topilmadi")

    user.password_hash = hash_password(data.new_password)
    user.token_version = (user.token_version or 1) + 1
    await db.commit()

    await redis.delete(f"otp:{data.phone}")
    await redis.delete(f"otp_verified:{data.phone}")

    return {"ok": True, "message": "Parol muvaffaqiyatli yangilandi"}


class RegisterSendOtpRequest(BaseModel):
    phone: str


class RegisterVerifyOtpRequest(BaseModel):
    phone: str
    code: str
    full_name: str
    password: str


@router.post("/register/send-otp")
@limiter.limit("3/hour")
async def register_send_otp(
    request: Request,
    data: RegisterSendOtpRequest,
    db: AsyncSession = Depends(get_db),
):
    """Step 1: Check phone availability and send OTP for registration."""
    existing = await db.execute(select(User).where(User.phone == data.phone))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Bu raqam allaqachon ro'yxatdan o'tgan")

    code = str(random.randint(100000, 999999))
    redis = await get_redis()
    await redis.setex(f"reg_otp:{data.phone}", OTP_TTL, code)

    sms_sent = await _send_otp_sms_text(
        data.phone,
        f"EduHub: Ro'yxatdan o'tish kodi: {code}. Amal qilish muddati 5 daqiqa.",
        db,
    )

    response = {"ok": True, "message": "Tasdiqlash kodi yuborildi"}
    if not sms_sent:
        response["code"] = code
    return response


@router.post("/register/verify-otp", response_model=UserOut, status_code=201)
@limiter.limit("5/hour")
async def register_verify_otp(
    request: Request,
    data: RegisterVerifyOtpRequest,
    db: AsyncSession = Depends(get_db),
):
    """Step 2: Verify OTP and complete registration."""
    redis = await get_redis()
    stored = await redis.get(f"reg_otp:{data.phone}")
    if not stored or stored != data.code:
        raise HTTPException(400, "Kod noto'g'ri yoki muddati o'tgan")

    existing = await db.execute(select(User).where(User.phone == data.phone))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Bu raqam allaqachon ro'yxatdan o'tgan")

    if len(data.password) < 8:
        raise HTTPException(400, "Parol kamida 8 ta belgi bo'lishi kerak")

    from app.models.user import UserRole
    user = User(
        full_name=data.full_name,
        phone=data.phone,
        password_hash=hash_password(data.password),
        role=UserRole.student,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    await redis.delete(f"reg_otp:{data.phone}")
    return user


@router.post("/change-password")
async def change_password(
    data: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(data.old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Eski parol noto'g'ri")
    if data.old_password == data.new_password:
        raise HTTPException(status_code=400, detail="Yangi parol eski parol bilan bir xil bo'lmasligi kerak")
    if len(data.new_password) < 8:
        raise HTTPException(status_code=400, detail="Yangi parol kamida 8 ta belgi bo'lishi kerak")
    current_user.password_hash = hash_password(data.new_password)
    current_user.token_version = (current_user.token_version or 1) + 1
    await db.commit()
    return {"ok": True, "message": "Parol muvaffaqiyatli o'zgartirildi"}
