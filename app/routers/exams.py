import json
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.exam import Exam, ExamQuestion, ExamSubmission, ExamDraft
from app.models.lesson import Lesson, Module
from app.schemas.exam import (
    ExamCreate, ExamUpdate, ExamOut, ExamQuestionOut,
    ExamSubmissionCreate, ExamSubmissionOut, ExamDraftIn, ExamDraftOut,
)
from app.dependencies import get_current_user, require_permission, teacher_course_ids, is_student

router = APIRouter(prefix="/exams", tags=["exams"])


def _lessons_in_courses(course_ids):
    """course_ids ichidagi kurslarga tegishli barcha dars id lari (subquery)."""
    return (
        select(Lesson.id)
        .join(Module, Module.id == Lesson.module_id)
        .where(Module.course_id.in_(course_ids))
    )


async def assert_teacher_teaches_exam(exam_id, current_user, db):
    """O'qituvchi bo'lsa — imtihon o'z faniga (o'qitadigan kursiga) tegishli ekanini tekshiradi."""
    course_ids = await teacher_course_ids(current_user, db)
    if course_ids is None:
        return
    res = await db.execute(
        select(Module.course_id)
        .join(Lesson, Lesson.module_id == Module.id)
        .join(Exam, Exam.lesson_id == Lesson.id)
        .where(Exam.id == exam_id)
    )
    cid = res.scalar_one_or_none()
    if cid is None or cid not in course_ids:
        raise HTTPException(403, "Bu imtihon sizning faningizga tegishli emas")


async def assert_teacher_teaches_lesson(lesson_id, current_user, db):
    """O'qituvchi bo'lsa — dars o'z faniga (o'qitadigan kursiga) tegishli ekanini tekshiradi."""
    course_ids = await teacher_course_ids(current_user, db)
    if course_ids is None:
        return
    if lesson_id is None:
        raise HTTPException(403, "O'qituvchi imtihonni o'z fanidagi darsga bog'lashi kerak")
    res = await db.execute(
        select(Module.course_id)
        .join(Lesson, Lesson.module_id == Module.id)
        .where(Lesson.id == lesson_id)
    )
    cid = res.scalar_one_or_none()
    if cid is None or cid not in course_ids:
        raise HTTPException(403, "Bu dars sizning faningizga tegishli emas")


def _build_exam_out(exam: Exam, draft: Optional[ExamDraft] = None) -> dict:
    questions = [ExamQuestionOut.from_orm_q(q) for q in (exam.questions or [])]
    draft_out = None
    if draft:
        try:
            answers = json.loads(draft.answers) if isinstance(draft.answers, str) else draft.answers
        except Exception:
            answers = []
        draft_out = ExamDraftOut(
            answers=answers,
            time_remaining_seconds=draft.time_remaining_seconds,
            started_at=draft.started_at,
        )
    return ExamOut(
        id=exam.id,
        lesson_id=exam.lesson_id,
        title=exam.title,
        type=exam.type,
        date=exam.date,
        time=exam.time,
        duration_minutes=exam.duration_minutes,
        pass_percent=exam.pass_percent,
        questions=questions,
        draft=draft_out,
    )


def _calculate_score(exam: Exam, answers: List[int]) -> tuple[int, bool]:
    """Javoblarni to'g'ri indekslar bilan solishtiradi, foizda ball qaytaradi."""
    questions = sorted(exam.questions or [], key=lambda q: q.order)
    if not questions:
        return 0, False
    correct = sum(
        1 for i, q in enumerate(questions)
        if i < len(answers) and answers[i] == q.correct_index
    )
    score = round(correct / len(questions) * 100)
    passed = score >= exam.pass_percent
    return score, passed


@router.get("", response_model=List[ExamOut])
async def list_exams(
    lesson_id: Optional[uuid.UUID] = Query(None),
    course_id: Optional[uuid.UUID] = Query(None),
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    q = select(Exam).options(selectinload(Exam.questions))
    if lesson_id:
        q = q.where(Exam.lesson_id == lesson_id)
    if course_id:
        # Berilgan kursning barcha darslariga tegishli imtihonlar (bitta so'rovda)
        q = q.where(Exam.lesson_id.in_(_lessons_in_courses([course_id])))
    # O'qituvchi bo'lsa — faqat o'zi o'qitadigan fan (kurs) imtihonlari.
    # Talaba/admin uchun cheklov yo'q (course_ids None qaytadi).
    course_ids = await teacher_course_ids(current_user, db)
    if course_ids is not None:
        q = q.where(Exam.lesson_id.in_(_lessons_in_courses(course_ids)))
    result = await db.execute(q.offset(skip).limit(limit))
    exams = result.scalars().all()
    # draft larini ham yukla
    out = []
    for exam in exams:
        draft_res = await db.execute(
            select(ExamDraft).where(
                ExamDraft.exam_id == exam.id,
                ExamDraft.student_id == current_user.id,
            )
        )
        draft = draft_res.scalar_one_or_none()
        out.append(_build_exam_out(exam, draft))
    return out


@router.post("", response_model=ExamOut, status_code=201)
async def create_exam(
    data: ExamCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("exams", "create")),
):
    # O'qituvchi faqat o'z fanidagi darsga imtihon yaratadi
    await assert_teacher_teaches_lesson(data.lesson_id, current_user, db)
    exam = Exam(**data.model_dump(exclude={"questions"}))
    db.add(exam)
    await db.flush()  # exam.id ni olish uchun
    for i, q in enumerate(data.questions or []):
        db.add(ExamQuestion(
            exam_id=exam.id,
            question=q.question,
            options=json.dumps(q.options, ensure_ascii=False),
            correct_index=q.correct_index,
            order=i,
        ))
    await db.commit()
    result = await db.execute(
        select(Exam).options(selectinload(Exam.questions)).where(Exam.id == exam.id)
    )
    return _build_exam_out(result.scalar_one(), None)


@router.get("/{exam_id}", response_model=ExamOut)
async def get_exam(
    exam_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        select(Exam).options(selectinload(Exam.questions)).where(Exam.id == exam_id)
    )
    exam = result.scalar_one_or_none()
    if not exam:
        raise HTTPException(404, "Exam not found")

    draft_res = await db.execute(
        select(ExamDraft).where(
            ExamDraft.exam_id == exam_id,
            ExamDraft.student_id == current_user.id,
        )
    )
    draft = draft_res.scalar_one_or_none()
    return _build_exam_out(exam, draft)


@router.patch("/{exam_id}", response_model=ExamOut)
async def update_exam(
    exam_id: uuid.UUID,
    data: ExamUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("exams", "update")),
):
    await assert_teacher_teaches_exam(exam_id, current_user, db)
    result = await db.execute(select(Exam).where(Exam.id == exam_id))
    exam = result.scalar_one_or_none()
    if not exam:
        raise HTTPException(404, "Exam not found")
    payload = data.model_dump(exclude_none=True)
    questions = payload.pop("questions", None)
    for k, v in payload.items():
        setattr(exam, k, v)
    if questions is not None:
        # Savollar berilsa — eskilarini o'chirib, yangilarini yozamiz
        await db.execute(delete(ExamQuestion).where(ExamQuestion.exam_id == exam_id))
        for i, q in enumerate(questions):
            db.add(ExamQuestion(
                exam_id=exam_id,
                question=q["question"],
                options=json.dumps(q["options"], ensure_ascii=False),
                correct_index=q["correct_index"],
                order=i,
            ))
    await db.commit()
    result = await db.execute(
        select(Exam).options(selectinload(Exam.questions)).where(Exam.id == exam_id)
    )
    return _build_exam_out(result.scalar_one(), None)


@router.delete("/{exam_id}", status_code=204)
async def delete_exam(
    exam_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("exams", "delete")),
):
    await assert_teacher_teaches_exam(exam_id, current_user, db)
    result = await db.execute(select(Exam).where(Exam.id == exam_id))
    exam = result.scalar_one_or_none()
    if not exam:
        raise HTTPException(404, "Exam not found")
    await db.delete(exam)
    await db.commit()


@router.post("/{exam_id}/save-draft")
async def save_draft(
    exam_id: uuid.UUID,
    data: ExamDraftIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Har bir javob tanlanganda chaqiriladi — oraliq javoblarni saqlaydi."""
    result = await db.execute(select(Exam).where(Exam.id == exam_id))
    if not result.scalar_one_or_none():
        raise HTTPException(404, "Exam not found")

    draft_res = await db.execute(
        select(ExamDraft).where(
            ExamDraft.exam_id == exam_id,
            ExamDraft.student_id == current_user.id,
        )
    )
    draft = draft_res.scalar_one_or_none()

    answers_json = json.dumps(data.answers)
    if draft:
        draft.answers = answers_json
        draft.time_remaining_seconds = data.time_remaining_seconds
    else:
        draft = ExamDraft(
            exam_id=exam_id,
            student_id=current_user.id,
            answers=answers_json,
            time_remaining_seconds=data.time_remaining_seconds,
        )
        db.add(draft)

    await db.commit()
    return {"ok": True}


@router.post("/{exam_id}/submit", response_model=ExamSubmissionOut, status_code=201)
async def submit_exam(
    exam_id: uuid.UUID,
    data: ExamSubmissionCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        select(Exam).options(selectinload(Exam.questions)).where(Exam.id == exam_id)
    )
    exam = result.scalar_one_or_none()
    if not exam:
        raise HTTPException(404, "Exam not found")

    score, passed = _calculate_score(exam, data.answers)

    submission = ExamSubmission(
        exam_id=exam_id,
        student_id=current_user.id,
        answers=json.dumps(data.answers),
        score=score,
        passed=passed,
        time_spent_seconds=data.time_spent_seconds,
    )
    db.add(submission)

    # Draft ni o'chirish — yakunlandi
    draft_res = await db.execute(
        select(ExamDraft).where(
            ExamDraft.exam_id == exam_id,
            ExamDraft.student_id == current_user.id,
        )
    )
    draft = draft_res.scalar_one_or_none()
    if draft:
        await db.delete(draft)

    await db.commit()
    await db.refresh(submission)
    return submission


@router.get("/{exam_id}/submissions", response_model=List[ExamSubmissionOut])
async def list_submissions(
    exam_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("exams", "view")),
):
    # O'qituvchi faqat o'z fani imtihonlari natijalarini ko'radi
    await assert_teacher_teaches_exam(exam_id, current_user, db)
    q = select(ExamSubmission).where(ExamSubmission.exam_id == exam_id)
    # O'quvchi faqat o'z natijasini ko'radi
    if is_student(current_user):
        q = q.where(ExamSubmission.student_id == current_user.id)
    result = await db.execute(q)
    return result.scalars().all()
