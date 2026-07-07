import uuid
import secrets
from decimal import Decimal
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import get_current_user
from app.models.card import Card, CardTransfer, _generate_card_number, _generate_expire, INITIAL_BALANCE

router = APIRouter(prefix="/cards", tags=["cards"])

ELIGIBLE_ROLES = {"student", "teacher", "assistant_teacher"}


class TransferRequest(BaseModel):
    to_card_number: str
    amount: Decimal
    note: Optional[str] = None


class TopUpRequest(BaseModel):
    amount: Decimal


def _card_out(card: Card):
    cn = card.card_number
    masked = f"{cn[:6]}******{cn[-4:]}" if len(cn) >= 10 else cn
    return {
        "id": str(card.id),
        "card_number": masked,
        "holder_name": card.holder_name,
        "expire": card.expire,
        "balance": float(card.balance),
        "status": card.status,
        "created_at": card.created_at.isoformat(),
    }


def _transfer_out(t: CardTransfer, my_card_id: uuid.UUID):
    direction = "sent" if t.from_card_id == my_card_id else "received"
    return {
        "id": str(t.id),
        "direction": direction,
        "amount": float(t.amount),
        "note": t.note,
        "status": t.status,
        "created_at": t.created_at.isoformat(),
    }


async def _get_or_create_card(user, db: AsyncSession) -> Card:
    if str(getattr(user, "role", "")) not in ELIGIBLE_ROLES:
        raise HTTPException(403, "Karta faqat o'quvchi/o'qituvchi uchun")
    result = await db.execute(select(Card).where(Card.user_id == user.id))
    card = result.scalar_one_or_none()
    if not card:
        card = Card(
            user_id=user.id,
            card_number=_generate_card_number(),
            holder_name=user.full_name or "FintechHub User",
            expire=_generate_expire(),
            balance=INITIAL_BALANCE,
            status="active",
        )
        db.add(card)
        await db.commit()
        await db.refresh(card)
    return card


@router.get("/my")
async def my_card(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    card = await _get_or_create_card(current_user, db)
    return _card_out(card)


@router.post("/lookup")
async def lookup_card(
    body: dict,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    card_number = body.get("card_number", "")
    result = await db.execute(select(Card).where(Card.card_number == card_number, Card.status == "active"))
    card = result.scalar_one_or_none()
    if not card:
        raise HTTPException(404, "Karta topilmadi")
    cn = card.card_number
    masked = f"{cn[:6]}******{cn[-4:]}" if len(cn) >= 10 else cn
    return {"card_number": masked, "holder_name": card.holder_name, "status": card.status}


@router.post("/topup")
async def top_up(
    data: TopUpRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if data.amount <= 0:
        raise HTTPException(400, "Summa 0 dan katta bo'lishi kerak")
    card = await _get_or_create_card(current_user, db)
    if card.status != "active":
        raise HTTPException(400, "Karta bloklangan")
    card.balance += data.amount
    await db.commit()
    await db.refresh(card)
    return _card_out(card)


@router.post("/transfer")
async def transfer(
    data: TransferRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if data.amount <= 0:
        raise HTTPException(400, "Summa 0 dan katta bo'lishi kerak")

    from_card = await _get_or_create_card(current_user, db)
    if from_card.status != "active":
        raise HTTPException(400, "Karta bloklangan")
    if from_card.card_number == data.to_card_number:
        raise HTTPException(400, "Bir xil kartaga o'tkazib bo'lmaydi")

    to_result = await db.execute(select(Card).where(Card.card_number == data.to_card_number))
    to_card = to_result.scalar_one_or_none()
    if not to_card:
        raise HTTPException(404, "Qabul qiluvchi karta topilmadi")
    if to_card.status != "active":
        raise HTTPException(400, "Qabul qiluvchi karta bloklangan")
    if from_card.balance < data.amount:
        raise HTTPException(400, "Yetarli mablag' yo'q")

    from_card.balance -= data.amount
    to_card.balance += data.amount

    transfer_record = CardTransfer(
        from_card_id=from_card.id,
        to_card_id=to_card.id,
        amount=data.amount,
        note=data.note,
        status="completed",
    )
    db.add(transfer_record)
    await db.commit()
    await db.refresh(from_card)
    return {**_card_out(from_card), "transfer_id": str(transfer_record.id)}


@router.get("/transfers")
async def transfers(
    skip: int = 0,
    limit: int = 20,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    card = await _get_or_create_card(current_user, db)
    from sqlalchemy import or_
    result = await db.execute(
        select(CardTransfer)
        .where(or_(CardTransfer.from_card_id == card.id, CardTransfer.to_card_id == card.id))
        .order_by(CardTransfer.created_at.desc())
        .offset(skip).limit(limit)
    )
    transfers_list = result.scalars().all()
    return [_transfer_out(t, card.id) for t in transfers_list]
