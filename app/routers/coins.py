import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models.coin import CoinTransaction
from app.models.group import Group, GroupStudent
from app.schemas.coin import CoinCreate, CoinOut
from app.dependencies import get_current_user, require_admin_or_teacher

router = APIRouter(prefix="/coins", tags=["coins"])


@router.get("", response_model=List[CoinOut])
async def list_coin_transactions(
    student_id: Optional[uuid.UUID] = Query(None),
    branch_id: Optional[str] = Query(None),
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(CoinTransaction)
    if student_id:
        q = q.where(CoinTransaction.student_id == student_id)
    if branch_id:
        q = q.where(CoinTransaction.student_id.in_(
            select(GroupStudent.student_id)
            .join(Group, Group.id == GroupStudent.group_id)
            .where(Group.branch_id == uuid.UUID(branch_id))
            .distinct()
        ))
    result = await db.execute(q.offset(skip).limit(limit).order_by(CoinTransaction.date.desc()))
    return result.scalars().all()


@router.post("", response_model=CoinOut, status_code=201)
async def create_coin_transaction(
    data: CoinCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin_or_teacher),
):
    txn = CoinTransaction(**data.model_dump())
    db.add(txn)
    await db.commit()
    await db.refresh(txn)
    return txn


@router.get("/balance/{student_id}")
async def get_coin_balance(
    student_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    result = await db.execute(
        select(func.coalesce(func.sum(CoinTransaction.coins), 0)).where(
            CoinTransaction.student_id == student_id
        )
    )
    balance = result.scalar()
    return {"student_id": student_id, "balance": balance}
