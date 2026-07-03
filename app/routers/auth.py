import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import get_current_user
from app.limiter import limiter
from app.models.user import User
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
