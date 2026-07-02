import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.exam import Exam, ExamSubmission
from app.schemas.exam import ExamCreate, ExamUpdate, ExamOut, ExamSubmissionCreate, ExamSubmissionOut
from app.dependencies import get_current_user, require_permission

router = APIRouter(prefix="/exams", tags=["exams"])


@router.get("", response_model=List[ExamOut])
async def list_exams(
    lesson_id: Optional[uuid.UUID] = Query(None),
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("exams", "view")),
):
    q = select(Exam)
    if lesson_id:
        q = q.where(Exam.lesson_id == lesson_id)
    result = await db.execute(q.offset(skip).limit(limit))
    return result.scalars().all()


@router.post("", response_model=ExamOut, status_code=201)
async def create_exam(
    data: ExamCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("exams", "create")),
):
    exam = Exam(**data.model_dump())
    db.add(exam)
    await db.commit()
    await db.refresh(exam)
    return exam


@router.get("/submissions", response_model=List[ExamSubmissionOut])
async def list_all_submissions(
    student_id: Optional[uuid.UUID] = Query(None),
    exam_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    q = select(ExamSubmission)
    if student_id:
        q = q.where(ExamSubmission.student_id == student_id)
    if exam_id:
        q = q.where(ExamSubmission.exam_id == exam_id)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/{exam_id}", response_model=ExamOut)
async def get_exam(
    exam_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    result = await db.execute(select(Exam).where(Exam.id == exam_id))
    exam = result.scalar_one_or_none()
    if not exam:
        raise HTTPException(404, "Exam not found")
    return exam


@router.patch("/{exam_id}", response_model=ExamOut)
async def update_exam(
    exam_id: uuid.UUID,
    data: ExamUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("exams", "update")),
):
    result = await db.execute(select(Exam).where(Exam.id == exam_id))
    exam = result.scalar_one_or_none()
    if not exam:
        raise HTTPException(404, "Exam not found")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(exam, k, v)
    await db.commit()
    await db.refresh(exam)
    return exam


@router.delete("/{exam_id}", status_code=204)
async def delete_exam(
    exam_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("exams", "delete")),
):
    result = await db.execute(select(Exam).where(Exam.id == exam_id))
    exam = result.scalar_one_or_none()
    if not exam:
        raise HTTPException(404, "Exam not found")
    await db.delete(exam)
    await db.commit()


@router.get("/{exam_id}/submissions", response_model=List[ExamSubmissionOut])
async def list_submissions(
    exam_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    result = await db.execute(select(ExamSubmission).where(ExamSubmission.exam_id == exam_id))
    return result.scalars().all()


@router.post("/{exam_id}/submit", response_model=ExamSubmissionOut, status_code=201)
async def submit_exam(
    exam_id: uuid.UUID,
    data: ExamSubmissionCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(Exam).where(Exam.id == exam_id))
    exam = result.scalar_one_or_none()
    if not exam:
        raise HTTPException(404, "Exam not found")
    submission = ExamSubmission(
        exam_id=exam_id,
        student_id=current_user.id,
        answers=data.answers,
        time_spent_seconds=data.time_spent_seconds,
    )
    db.add(submission)
    await db.commit()
    await db.refresh(submission)
    return submission
