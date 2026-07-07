import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.models.lesson_homework import (
    LessonHomework, LessonHomeworkSubmission,
    HomeworkType, SubmissionStatus,
)

router = APIRouter(prefix="/lessons", tags=["lesson-homework"])


# ─── Schemas ──────────────────────────────────────────────────────────────────
class HomeworkCreate(BaseModel):
    title: str
    description: Optional[str] = None
    type: HomeworkType = HomeworkType.text
    max_score: int = 100
    order: int = 0
    is_required: bool = True
    config: Optional[dict] = None


class HomeworkUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    type: Optional[HomeworkType] = None
    max_score: Optional[int] = None
    order: Optional[int] = None
    is_required: Optional[bool] = None
    config: Optional[dict] = None


class SubmitPayload(BaseModel):
    group_id: Optional[uuid.UUID] = None
    text_answer: Optional[str] = None
    file_url: Optional[str] = None
    github_url: Optional[str] = None
    code_answer: Optional[str] = None
    quiz_answers: Optional[list] = None


class GradePayload(BaseModel):
    score: Optional[int] = None
    feedback: Optional[str] = None
    status: Optional[SubmissionStatus] = None


def _hw(h: LessonHomework) -> dict:
    return {
        "id": str(h.id),
        "lesson_id": str(h.lesson_id),
        "title": h.title,
        "description": h.description,
        "type": h.type,
        "max_score": h.max_score,
        "order": h.order,
        "is_required": h.is_required,
        "config": h.config,
    }


def _sub(s: LessonHomeworkSubmission) -> dict:
    return {
        "id": str(s.id),
        "homework_id": str(s.homework_id),
        "student_id": str(s.student_id),
        "student_name": s.student.full_name if s.student else None,
        "group_id": str(s.group_id) if s.group_id else None,
        "text_answer": s.text_answer,
        "file_url": s.file_url,
        "github_url": s.github_url,
        "code_answer": s.code_answer,
        "quiz_answers": s.quiz_answers,
        "score": s.score,
        "feedback": s.feedback,
        "status": s.status,
        "submitted_at": s.submitted_at.isoformat(),
    }


# ─── Homework CRUD ────────────────────────────────────────────────────────────

@router.get("/{lesson_id}/homework")
async def list_homework(
    lesson_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    rows = (await db.execute(
        select(LessonHomework)
        .where(LessonHomework.lesson_id == lesson_id)
        .order_by(LessonHomework.order, LessonHomework.created_at)
    )).scalars().all()
    return [_hw(r) for r in rows]


@router.post("/{lesson_id}/homework", status_code=201)
async def create_homework(
    lesson_id: uuid.UUID,
    data: HomeworkCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("courses", "update")),
):
    hw = LessonHomework(lesson_id=lesson_id, **data.model_dump())
    db.add(hw)
    await db.commit()
    await db.refresh(hw)
    return _hw(hw)


@router.patch("/homework/{hw_id}")
async def update_homework(
    hw_id: uuid.UUID,
    data: HomeworkUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("courses", "update")),
):
    hw = (await db.execute(select(LessonHomework).where(LessonHomework.id == hw_id))).scalar_one_or_none()
    if not hw:
        raise HTTPException(404, "Uy vazifa topilmadi")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(hw, k, v)
    await db.commit()
    await db.refresh(hw)
    return _hw(hw)


@router.delete("/homework/{hw_id}", status_code=204)
async def delete_homework(
    hw_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("courses", "delete")),
):
    hw = (await db.execute(select(LessonHomework).where(LessonHomework.id == hw_id))).scalar_one_or_none()
    if not hw:
        raise HTTPException(404, "Uy vazifa topilmadi")
    await db.delete(hw)
    await db.commit()


# ─── Student submissions ──────────────────────────────────────────────────────

@router.post("/homework/{hw_id}/submit", status_code=201)
async def submit_homework(
    hw_id: uuid.UUID,
    data: SubmitPayload,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    hw = (await db.execute(select(LessonHomework).where(LessonHomework.id == hw_id))).scalar_one_or_none()
    if not hw:
        raise HTTPException(404, "Uy vazifa topilmadi")

    existing = (await db.execute(
        select(LessonHomeworkSubmission).where(
            LessonHomeworkSubmission.homework_id == hw_id,
            LessonHomeworkSubmission.student_id == current_user.id,
        )
    )).scalar_one_or_none()

    if existing:
        for k, v in data.model_dump(exclude_none=True).items():
            setattr(existing, k, v)
        existing.status = SubmissionStatus.submitted
        await db.commit()
        sub_id = existing.id
    else:
        sub = LessonHomeworkSubmission(
            homework_id=hw_id,
            student_id=current_user.id,
            status=SubmissionStatus.submitted,
            **data.model_dump(exclude_none=True),
        )
        db.add(sub)
        await db.commit()
        sub_id = sub.id

    result = await db.execute(
        select(LessonHomeworkSubmission)
        .options(selectinload(LessonHomeworkSubmission.student))
        .where(LessonHomeworkSubmission.id == sub_id)
    )
    return _sub(result.scalar_one())


@router.get("/homework/my/{lesson_id}")
async def my_submissions(
    lesson_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    hw_rows = (await db.execute(
        select(LessonHomework.id).where(LessonHomework.lesson_id == lesson_id)
    )).scalars().all()
    if not hw_rows:
        return []
    rows = (await db.execute(
        select(LessonHomeworkSubmission)
        .where(
            LessonHomeworkSubmission.homework_id.in_(hw_rows),
            LessonHomeworkSubmission.student_id == current_user.id,
        )
    )).scalars().all()
    return [_sub(r) for r in rows]


@router.get("/homework/{hw_id}/submissions")
async def get_submissions(
    hw_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("courses", "view")),
):
    rows = (await db.execute(
        select(LessonHomeworkSubmission)
        .options(selectinload(LessonHomeworkSubmission.student))
        .where(LessonHomeworkSubmission.homework_id == hw_id)
        .order_by(LessonHomeworkSubmission.submitted_at.desc())
    )).scalars().all()
    return [_sub(r) for r in rows]


@router.patch("/homework/submissions/{sub_id}")
async def grade_submission(
    sub_id: uuid.UUID,
    data: GradePayload,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("courses", "update")),
):
    sub = (await db.execute(select(LessonHomeworkSubmission).where(LessonHomeworkSubmission.id == sub_id))).scalar_one_or_none()
    if not sub:
        raise HTTPException(404, "Submission topilmadi")
    if data.score is not None:
        sub.score = data.score
    if data.feedback is not None:
        sub.feedback = data.feedback
    if data.status is not None:
        sub.status = data.status
    await db.commit()
    await db.refresh(sub)
    return _sub(sub)
