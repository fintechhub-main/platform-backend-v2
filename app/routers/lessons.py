import uuid
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List, Optional

from app.database import get_db
from app.models.lesson import Module, Lesson, QuizQuestion
from app.models.group_progress import GroupLessonDone
from app.schemas.lesson import (
    ModuleCreate, ModuleUpdate, ModuleOut, ModuleWithLessons,
    LessonCreate, LessonUpdate, LessonOut,
    QuizQuestionCreate, QuizQuestionUpdate, QuizQuestionOut,
)
from app.dependencies import get_current_user, require_permission, is_student
from app.services.notify import notify_users_bulk
from app.models.group import GroupStudent
from app.models.lesson import Module

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
    mods = result.scalars().all()
    if not is_student(_):
        return mods
    # O'quvchiga: yopiq darslarning kontenti/video havolasi yuborilmaydi
    open_ids = set()
    gl = await db.execute(
        select(GroupLessonDone.lesson_id)
        .join(GroupStudent, GroupStudent.group_id == GroupLessonDone.group_id)
        .where(GroupStudent.student_id == _.id, GroupLessonDone.is_open == True)  # noqa: E712
    )
    open_ids = {str(r) for r in gl.scalars().all()}
    out = []
    for m in mods:
        mo = ModuleWithLessons.model_validate(m).model_dump()
        for l in mo.get("lessons", []):
            if not (l.get("is_open") or str(l.get("id")) in open_ids):
                l["content"] = None
                l["video_url"] = None
        out.append(mo)
    return out


@router.get("/slim")
async def list_lessons_slim(
    course_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Yengil dars ro'yxati — faqat id, title, modul nomi (picker uchun)."""
    rows = (await db.execute(
        select(Lesson.id, Lesson.title, Module.title, Module.order, Lesson.order)
        .join(Module, Module.id == Lesson.module_id)
        .where(Module.course_id == course_id)
        .order_by(Module.order, Lesson.order)
    )).all()
    return [{"id": str(r[0]), "title": r[1], "module_name": r[2]} for r in rows]


@router.post("/modules", response_model=ModuleOut, status_code=201)
async def create_module(data: ModuleCreate, db: AsyncSession = Depends(get_db), _=Depends(require_permission("courses", "create"))):
    module = Module(**data.model_dump())
    db.add(module)
    await db.commit()
    await db.refresh(module)
    return module


@router.patch("/modules/{module_id}", response_model=ModuleOut)
async def update_module(module_id: uuid.UUID, data: ModuleUpdate, db: AsyncSession = Depends(get_db), _=Depends(require_permission("courses", "update"))):
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
async def delete_module(module_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(require_permission("courses", "delete"))):
    result = await db.execute(select(Module).where(Module.id == module_id))
    module = result.scalar_one_or_none()
    if not module:
        raise HTTPException(404, "Module not found")
    await db.delete(module)
    await db.commit()


# ── Lessons ───────────────────────────────────────────────────────────────────

@router.post("", response_model=LessonOut, status_code=201)
async def create_lesson(data: LessonCreate, db: AsyncSession = Depends(get_db), _=Depends(require_permission("courses", "create"))):
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
async def update_lesson(lesson_id: uuid.UUID, data: LessonUpdate, db: AsyncSession = Depends(get_db), _=Depends(require_permission("courses", "update"))):
    result = await db.execute(select(Lesson).where(Lesson.id == lesson_id))
    lesson = result.scalar_one_or_none()
    if not lesson:
        raise HTTPException(404, "Lesson not found")
    was_open = lesson.is_open
    update_data = data.model_dump(exclude_none=True)
    for k, v in update_data.items():
        setattr(lesson, k, v)
    await db.commit()
    await db.refresh(lesson)
    # Notify students when lesson becomes open
    if not was_open and lesson.is_open:
        mod_result = await db.execute(select(Module).where(Module.id == lesson.module_id))
        module = mod_result.scalar_one_or_none()
        students_result = await db.execute(
            select(GroupStudent.student_id).join(
                __import__("app.models.group", fromlist=["Group"]).Group,
                GroupStudent.group_id == __import__("app.models.group", fromlist=["Group"]).Group.id,
            ).where(
                __import__("app.models.group", fromlist=["Group"]).Group.course_id == (module.course_id if module else None)
            ).distinct()
        )
        student_ids = [r[0] for r in students_result.all()]
        if student_ids:
            await notify_users_bulk(
                db, student_ids,
                title="Yangi darslik ochildi! 📖",
                body=lesson.title,
                notification_type="lesson_open",
                data={"lesson_id": str(lesson.id)},
            )
            await db.commit()
    return lesson


@router.delete("/{lesson_id}", status_code=204)
async def delete_lesson(lesson_id: uuid.UUID, db: AsyncSession = Depends(get_db), _=Depends(require_permission("courses", "delete"))):
    result = await db.execute(select(Lesson).where(Lesson.id == lesson_id))
    lesson = result.scalar_one_or_none()
    if not lesson:
        raise HTTPException(404, "Lesson not found")
    await db.delete(lesson)
    await db.commit()


# ── Quiz Questions ─────────────────────────────────────────────────────────────

@router.get("/{lesson_id}/quiz")
async def list_quiz(lesson_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                    current_user=Depends(get_current_user)):
    result = await db.execute(
        select(QuizQuestion).where(QuizQuestion.lesson_id == lesson_id).order_by(QuizQuestion.order)
    )
    rows = result.scalars().all()
    hide = is_student(current_user)   # o'quvchiga to'g'ri javob ko'rsatilmaydi
    out = []
    for q in rows:
        try:
            opts = json.loads(q.options) if isinstance(q.options, str) else (q.options or [])
        except Exception:
            opts = []
        item = {"id": str(q.id), "lesson_id": str(q.lesson_id), "question": q.question,
                "options": opts, "order": q.order}
        if not hide:
            item["correct_index"] = q.correct_index
        out.append(item)
    return out


@router.post("/{lesson_id}/quiz/check")
async def check_quiz(lesson_id: uuid.UUID, data: dict,
                     db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Javoblarni server tomonda tekshiradi. data: {"answers": [0,2,1,...]}"""
    rows = (await db.execute(
        select(QuizQuestion).where(QuizQuestion.lesson_id == lesson_id).order_by(QuizQuestion.order)
    )).scalars().all()
    answers = data.get("answers") or []
    results, correct = [], 0
    for i, q in enumerate(rows):
        a = answers[i] if i < len(answers) else None
        ok = (a == q.correct_index)
        if ok:
            correct += 1
        results.append({"question_id": str(q.id), "your_answer": a,
                        "correct_index": q.correct_index, "is_correct": ok})
    total = len(rows)
    return {"total": total, "correct": correct,
            "score": round(correct / total * 100) if total else 0,
            "results": results}


@router.post("/{lesson_id}/quiz", response_model=QuizQuestionOut, status_code=201)
async def create_quiz_question(
    lesson_id: uuid.UUID, data: QuizQuestionCreate,
    db: AsyncSession = Depends(get_db), _=Depends(require_permission("courses", "create")),
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
    db: AsyncSession = Depends(get_db), _=Depends(require_permission("courses", "update")),
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
    db: AsyncSession = Depends(get_db), _=Depends(require_permission("courses", "delete")),
):
    result = await db.execute(select(QuizQuestion).where(QuizQuestion.id == question_id))
    q = result.scalar_one_or_none()
    if not q:
        raise HTTPException(404, "Question not found")
    await db.delete(q)
    await db.commit()
