import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.homework import HomeworkSubmission
from app.schemas.homework import HomeworkCreate, HomeworkUpdate, HomeworkOut
from app.dependencies import get_current_user, require_admin_or_teacher, require_permission

router = APIRouter(prefix="/homework", tags=["homework"])


@router.get("", response_model=List[HomeworkOut])
async def list_homework(
    lesson_id: Optional[uuid.UUID] = Query(None),
    student_id: Optional[uuid.UUID] = Query(None),
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("homework", "view")),
):
    q = select(HomeworkSubmission)
    if lesson_id:
        q = q.where(HomeworkSubmission.lesson_id == lesson_id)
    if student_id:
        q = q.where(HomeworkSubmission.student_id == student_id)
    result = await db.execute(q.offset(skip).limit(limit))
    return result.scalars().all()


@router.post("", response_model=HomeworkOut, status_code=201)
async def create_homework(
    data: HomeworkCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin_or_teacher),
):
    submission = HomeworkSubmission(**data.model_dump())
    db.add(submission)
    await db.commit()
    await db.refresh(submission)
    return submission


@router.patch("/{homework_id}", response_model=HomeworkOut)
async def update_homework(
    homework_id: uuid.UUID,
    data: HomeworkUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin_or_teacher),
):
    result = await db.execute(select(HomeworkSubmission).where(HomeworkSubmission.id == homework_id))
    submission = result.scalar_one_or_none()
    if not submission:
        raise HTTPException(404, "Homework submission not found")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(submission, k, v)
    await db.commit()
    await db.refresh(submission)
    return submission
