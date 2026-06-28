import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.discount import Discount
from app.models.user import User
from app.schemas.discount import DiscountCreate, DiscountUpdate, DiscountOut
from app.dependencies import get_current_user, require_admin

router = APIRouter(prefix="/discounts", tags=["discounts"])


@router.get("", response_model=List[DiscountOut])
async def list_discounts(
    student_id: Optional[uuid.UUID] = Query(None),
    group_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = (
        select(Discount, User.full_name, User.phone)
        .join(User, User.id == Discount.student_id)
    )
    if student_id:
        q = q.where(Discount.student_id == student_id)
    if group_id:
        q = q.where(Discount.group_id == group_id)
    rows = (await db.execute(q.order_by(Discount.start_date.desc().nulls_last()))).all()
    result = []
    for discount, full_name, phone in rows:
        d = DiscountOut.model_validate(discount)
        d.student_name = full_name
        d.student_phone = phone
        result.append(d)
    return result


@router.post("", response_model=DiscountOut, status_code=201)
async def create_discount(data: DiscountCreate, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    discount = Discount(**data.model_dump())
    db.add(discount)
    await db.commit()
    await db.refresh(discount)
    return discount


@router.patch("/{discount_id}", response_model=DiscountOut)
async def update_discount(discount_id: uuid.UUID, data: DiscountUpdate, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(Discount).where(Discount.id == discount_id))
    discount = result.scalar_one_or_none()
    if not discount:
        raise HTTPException(404, "Discount not found")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(discount, k, v)
    await db.commit()
    await db.refresh(discount)
    return discount


@router.delete("/{discount_id}", status_code=204)
async def delete_discount(discount_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(Discount).where(Discount.id == discount_id))
    discount = result.scalar_one_or_none()
    if not discount:
        raise HTTPException(404, "Not found")
    await db.delete(discount)
    await db.commit()
