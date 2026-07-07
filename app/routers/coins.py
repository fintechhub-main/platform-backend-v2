import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models.coin import CoinTransaction
from app.models.coin_rule import CoinRule
from app.models.group import Group, GroupStudent
from app.models.user import User
from app.schemas.coin import CoinCreate, CoinOut
from app.dependencies import get_current_user, require_permission

router = APIRouter(prefix="/coins", tags=["coins"])

# ─── Default seed data ────────────────────────────────────────────────────────
DEFAULT_COIN_RULES = [
    {"name": "Darsga kelish",      "description": "5/5 davomatda bonus",                  "coins": 5,   "enabled": True,  "category": "Davomat"},
    {"name": "Uy vazifa 5/5",      "description": "Barcha uy vazifalarni bajarish",        "coins": 10,  "enabled": True,  "category": "Vazifa" },
    {"name": "Imtihon A",          "description": "Imtihonda A baho olish",                "coins": 20,  "enabled": True,  "category": "Imtihon"},
    {"name": "Hafta reytingi #1",  "description": "Haftalik reytingda birinchi o'rin",     "coins": 50,  "enabled": True,  "category": "Reyting"},
    {"name": "30 kun ketma-ket",   "description": "30 kunlik uzluksiz streak",             "coins": 100, "enabled": True,  "category": "Streak" },
    {"name": "Guruh yordamchisi",  "description": "Guruh topshirig'ida yordam berish",     "coins": 15,  "enabled": False, "category": "Faollik"},
    {"name": "Tug'ilgan kun",      "description": "Tug'ilgan kun bonusi",                  "coins": 30,  "enabled": True,  "category": "Maxsus" },
]


class RuleUpdate(BaseModel):
    enabled: Optional[bool] = None
    coins: Optional[int] = None


@router.get("", response_model=List[CoinOut])
async def list_coin_transactions(
    student_id: Optional[uuid.UUID] = Query(None),
    branch_id: Optional[str] = Query(None),
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("coins", "view")),
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
    _=Depends(require_permission("coins", "create")),
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
    current_user: User = Depends(get_current_user),
):
    if str(current_user.role) == "student" and current_user.id != student_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")
    result = await db.execute(
        select(func.coalesce(func.sum(CoinTransaction.coins), 0)).where(
            CoinTransaction.student_id == student_id
        )
    )
    balance = result.scalar()
    return {"student_id": student_id, "balance": balance}


# ─── Coin rules ───────────────────────────────────────────────────────────────

def _rule_out(r: CoinRule):
    return {
        "id": r.id,
        "name": r.name,
        "description": r.description,
        "coins": r.coins,
        "enabled": r.enabled,
        "category": r.category,
    }


@router.get("/rules")
async def list_coin_rules(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("coins", "view")),
):
    rows = (await db.execute(select(CoinRule).order_by(CoinRule.id))).scalars().all()
    if not rows:
        # Seed defaults on first call
        for d in DEFAULT_COIN_RULES:
            db.add(CoinRule(**d))
        await db.commit()
        rows = (await db.execute(select(CoinRule).order_by(CoinRule.id))).scalars().all()
    return [_rule_out(r) for r in rows]


@router.patch("/rules/{rule_id}")
async def update_coin_rule(
    rule_id: int,
    data: RuleUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("coins", "update")),
):
    row = (await db.execute(select(CoinRule).where(CoinRule.id == rule_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Qoida topilmadi")
    if data.enabled is not None:
        row.enabled = data.enabled
    if data.coins is not None:
        row.coins = max(1, data.coins)
    await db.commit()
    await db.refresh(row)
    return _rule_out(row)
