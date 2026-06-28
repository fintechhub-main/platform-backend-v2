import uuid
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List, Optional

from app.database import get_db
from app.models.lesson import Module, Lesson, QuizQuestion
from app.schemas.lesson import (
    ModuleCreate, ModuleUpdate, ModuleOut, ModuleWithLessons,
    LessonCreate, LessonUpdate, LessonOut,
    QuizQuestionCreate, QuizQuestionUpdate, QuizQuestionOut,
)
from app.dependencies import get_current_user, require_admin_or_teacher

router = APIRouter(prefix="/lessons", tags=["lessons"])


# ── Modules ──────────────────────────────────────────────────────────────────

@router.get("/modules", response_model=List[ModuleWithLessons])
async def list_modules(
    course_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    result = await db.execute(
        select(Module)
        .options(selectinload(Module.lessons).selectinload(Lesson.quiz_questions))
        .where(Module.course_id == course_id)
        .order_by(Module.order)
    )
    return result.scalars().all()


@router.post("/modules", response_model=ModuleOut, status_code=201)
async def create_module(data: ModuleCreate, db: AsyncSession = Depends(get_db), _=Depends(require_admin_or_teacher)):
    module = Module(**data.model_dump())
    db.add(module)
    await db.commit()
    await db.refresh(module)
    return module


@router.patch("/modules/{module_id}", response_model=ModuleOut)
async def update_module(module_id: uuid.UUID, data: ModuleUpdate, db: AsyncSession = Depends(get_db), _=Depends(require_admin_or_teacher)):
    result = await db.execute(select(Module).where(Module.id == module_id))
    module = result.scalar_one_or_none()
    if not module:
        raise HTTPException(404, "Module not found")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(module, k, v)
    await db.commit()
    await db.refresh(module)
    return module


@router.delete("/modules/{module_id}", status_code=204)
async def delete_module(module_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(require_admin_or_teacher)):
    result = await db.execute(select(Module).where(Module.id == module_id))
    module = result.scalar_one_or_none()
    if not module:
        raise HTTPException(404, "Module not found")
    await db.delete(module)
    await db.commit()


# ── Lessons ───────────────────────────────────────────────────────────────────

@router.post("", response_model=LessonOut, status_code=201)
async def create_lesson(data: LessonCreate, db: AsyncSession = Depends(get_db), _=Depends(require_admin_or_teacher)):
    lesson = Lesson(**data.model_dump())
    db.add(lesson)
    await db.commit()
    await db.refresh(lesson)
    return lesson


@router.get("/{lesson_id}", response_model=LessonOut)
async def get_lesson(lesson_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(select(Lesson).where(Lesson.id == lesson_id))
    lesson = result.scalar_one_or_none()
    if not lesson:
        raise HTTPException(404, "Lesson not found")
    return lesson


@router.patch("/{lesson_id}", response_model=LessonOut)
async def update_lesson(lesson_id: uuid.UUID, data: LessonUpdate, db: AsyncSession = Depends(get_db), _=Depends(require_admin_or_teacher)):
    result = await db.execute(select(Lesson).where(Lesson.id == lesson_id))
    lesson = result.scalar_one_or_none()
    if not lesson:
        raise HTTPException(404, "Lesson not found")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(lesson, k, v)
    await db.commit()
    await db.refresh(lesson)
    return lesson


@router.delete("/{lesson_id}", status_code=204)
async def delete_lesson(lesson_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(require_admin_or_teacher)):
    result = await db.execute(select(Lesson).where(Lesson.id == lesson_id))
    lesson = result.scalar_one_or_none()
    if not lesson:
        raise HTTPException(404, "Lesson not found")
    await db.delete(lesson)
    await db.commit()


# ── Quiz Questions ─────────────────────────────────────────────────────────────

@router.get("/{lesson_id}/quiz", response_model=List[QuizQuestionOut])
async def list_quiz(lesson_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(
        select(QuizQuestion).where(QuizQuestion.lesson_id == lesson_id).order_by(QuizQuestion.order)
    )
    return result.scalars().all()


@router.post("/{lesson_id}/quiz", response_model=QuizQuestionOut, status_code=201)
async def create_quiz_question(
    lesson_id: uuid.UUID, data: QuizQuestionCreate,
    db: AsyncSession = Depends(get_db), _=Depends(require_admin_or_teacher),
):
    q = QuizQuestion(
        lesson_id=lesson_id,
        question=data.question,
        options=json.dumps(data.options, ensure_ascii=False),
        correct_index=data.correct_index,
        order=data.order,
    )
    db.add(q)
    await db.commit()
    await db.refresh(q)
    return q


@router.patch("/quiz/{question_id}", response_model=QuizQuestionOut)
async def update_quiz_question(
    question_id: uuid.UUID, data: QuizQuestionUpdate,
    db: AsyncSession = Depends(get_db), _=Depends(require_admin_or_teacher),
):
    result = await db.execute(select(QuizQuestion).where(QuizQuestion.id == question_id))
    q = result.scalar_one_or_none()
    if not q:
        raise HTTPException(404, "Question not found")
    if data.question is not None:
        q.question = data.question
    if data.options is not None:
        q.options = json.dumps(data.options, ensure_ascii=False)
    if data.correct_index is not None:
        q.correct_index = data.correct_index
    if data.order is not None:
        q.order = data.order
    await db.commit()
    await db.refresh(q)
    return q


@router.delete("/quiz/{question_id}", status_code=204)
async def delete_quiz_question(
    question_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), _=Depends(require_admin_or_teacher),
):
    result = await db.execute(select(QuizQuestion).where(QuizQuestion.id == question_id))
    q = result.scalar_one_or_none()
    if not q:
        raise HTTPException(404, "Question not found")
    await db.delete(q)
    await db.commit()
