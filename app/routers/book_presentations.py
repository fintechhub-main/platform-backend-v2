import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.models.book_presentation import BookPresentation

router = APIRouter(prefix="/book-presentations", tags=["book-presentations"])


class BookPresentationCreate(BaseModel):
    name_of_book: str
    group_id: Optional[str] = None
    date_presentation: Optional[str] = None
    ball_of_presentation: int = 0
    is_presented: bool = False
    file: Optional[str] = None


class BookPresentationUpdate(BaseModel):
    name_of_book: Optional[str] = None
    group_id: Optional[str] = None
    date_presentation: Optional[str] = None
    ball_of_presentation: Optional[int] = None
    is_presented: Optional[bool] = None
    file: Optional[str] = None


def _out(b: BookPresentation):
    return {
        "id": str(b.id),
        "user_id": str(b.user_id) if b.user_id else None,
        "group_id": str(b.group_id) if b.group_id else None,
        "name_of_book": b.name_of_book,
        "date_presentation": str(b.date_presentation) if b.date_presentation else None,
        "ball_of_presentation": b.ball_of_presentation,
        "is_presented": b.is_presented,
        "file": b.file,
        "created_at": b.created_at.isoformat(),
    }


@router.get("")
async def list_book_presentations(
    group_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    is_presented: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(BookPresentation)
    role = str(getattr(current_user, "role", ""))
    if role == "student":
        q = q.where(BookPresentation.user_id == current_user.id)
    else:
        if user_id:
            q = q.where(BookPresentation.user_id == uuid.UUID(user_id))
        if group_id:
            q = q.where(BookPresentation.group_id == uuid.UUID(group_id))
    if is_presented is not None:
        q = q.where(BookPresentation.is_presented == is_presented)
    q = q.order_by(BookPresentation.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    return [_out(b) for b in result.scalars().all()]


@router.post("", status_code=201)
async def create_book_presentation(
    data: BookPresentationCreate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from datetime import date
    obj = BookPresentation(
        user_id=current_user.id,
        name_of_book=data.name_of_book,
        group_id=uuid.UUID(data.group_id) if data.group_id else None,
        ball_of_presentation=data.ball_of_presentation,
        is_presented=data.is_presented,
        file=data.file,
    )
    if data.date_presentation:
        obj.date_presentation = date.fromisoformat(data.date_presentation)
    if data.is_presented and not data.date_presentation:
        obj.date_presentation = date.today()
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return _out(obj)


@router.patch("/{book_id}")
async def update_book_presentation(
    book_id: uuid.UUID,
    data: BookPresentationUpdate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(BookPresentation).where(BookPresentation.id == book_id))
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Topilmadi")

    role = str(getattr(current_user, "role", ""))
    if role == "student" and obj.user_id != current_user.id:
        raise HTTPException(403, "Ruxsat yo'q")

    updates = data.model_dump(exclude_unset=True)
    from datetime import date
    if "date_presentation" in updates and updates["date_presentation"]:
        obj.date_presentation = date.fromisoformat(updates.pop("date_presentation"))
    if "group_id" in updates:
        obj.group_id = uuid.UUID(updates.pop("group_id")) if updates["group_id"] else None
    if updates.get("is_presented") and not obj.date_presentation:
        obj.date_presentation = date.today()
    for k, v in updates.items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return _out(obj)


@router.delete("/{book_id}", status_code=204)
async def delete_book_presentation(
    book_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(BookPresentation).where(BookPresentation.id == book_id))
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Topilmadi")
    role = str(getattr(current_user, "role", ""))
    if role == "student" and obj.user_id != current_user.id:
        raise HTTPException(403, "Ruxsat yo'q")
    await db.delete(obj)
    await db.commit()
