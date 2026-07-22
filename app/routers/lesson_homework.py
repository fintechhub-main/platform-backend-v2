import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import (
    get_current_user, require_permission, is_student, check_permission)
from app.models.group import Group, GroupStudent
from app.models.group_progress import GroupLessonDone
from app.models.lesson import Lesson, Module
from app.models.user import User
from app.services import hw_grader
from app.services.notify import notify_user
from app.utils import uploads as up
from app.utils.tz import local_now
from app.utils.student_scope import open_lesson_ids
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
    file_name: Optional[str] = None
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
        "ai_score": s.ai_score,
        "ai_feedback": s.ai_feedback,
        "graded_by": str(s.graded_by) if s.graded_by else None,
        "graded_at": s.graded_at.isoformat() if s.graded_at else None,
        "file_name": s.file_name,
        "status": s.status,
        "submitted_at": s.submitted_at.isoformat(),
    }



# ─── O'quvchi uchun: ochilgan darslarning barcha uy vazifalari ────────────────

@router.get("/homework/student/list")
async def student_homework_list(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """O'quvchining ochilgan darsliklaridagi uy vazifalar + bajarilgan holati."""
    open_ids = await open_lesson_ids(db, current_user.id)
    if not open_ids:
        return []

    rows = (await db.execute(
        select(LessonHomework, Lesson.title, Module.title, Module.order, Lesson.order)
        .join(Lesson, Lesson.id == LessonHomework.lesson_id)
        .join(Module, Module.id == Lesson.module_id)
        .where(LessonHomework.lesson_id.in_(open_ids))
        .order_by(Module.order, Lesson.order, LessonHomework.order)
    )).all()
    if not rows:
        return []

    subs = {
        s.homework_id: s for s in (await db.execute(
            select(LessonHomeworkSubmission).where(
                LessonHomeworkSubmission.student_id == current_user.id,
                LessonHomeworkSubmission.homework_id.in_([r[0].id for r in rows]),
            )
        )).scalars().all()
    }

    out = []
    for hw, lesson_title, module_title, _mo, _lo in rows:
        sub = subs.get(hw.id)
        out.append({
            **_hw(hw),
            "lesson_title": lesson_title,
            "module_title": module_title,
            "is_done": sub is not None and sub.status != SubmissionStatus.pending,
            "submission": _sub_light(sub) if sub else None,
        })
    return out


def _sub_light(s) -> dict:
    return {
        "id": str(s.id),
        "text_answer": s.text_answer,
        "file_url": s.file_url,
        "file_name": s.file_name,
        "github_url": s.github_url,
        "score": s.score,
        "ai_score": s.ai_score,
        "ai_feedback": s.ai_feedback,
        "feedback": s.feedback,
        "status": s.status,
        "graded_by": str(s.graded_by) if s.graded_by else None,
        "submitted_at": s.submitted_at.isoformat() if s.submitted_at else None,
    }


# ─── Fayl yuklash / berish ────────────────────────────────────────────────────

@router.post("/homework/upload", status_code=201)
async def upload_homework_file(
    file: UploadFile = File(...),
    _=Depends(get_current_user),
):
    """Rasm yoki PDF yuklash. Tekshiruvlar app/utils/uploads.py da."""
    stored, original, size = await up.save_upload(file)
    return {
        "file_url": f"/api/v1/lessons/homework/file/{up.to_slug(stored)}",
        "file_name": original,
        "size": size,
    }


@router.get("/homework/file/{slug}")
async def get_homework_file(slug: str, _=Depends(get_current_user)):
    path, mime = up.resolve_stored(slug)
    return FileResponse(path, media_type=mime)


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
    sub = result.scalar_one()

    # ── AI avto-baholash (5 ballik) ──────────────────────────────────────────
    # AI ishlamasa topshiriq "submitted" holatida qoladi — ustoz qo'lda baholaydi.
    score, feedback = await hw_grader.ai_grade(db, hw, sub)
    if score is not None:
        sub.ai_score = score
        sub.ai_feedback = feedback
        sub.score = score                     # boshlang'ich baho — ustoz o'zgartira oladi
        sub.feedback = feedback
        sub.status = SubmissionStatus.graded
        sub.graded_at = local_now()
        await db.commit()
        await db.refresh(sub)
        try:
            await notify_user(db, sub.student_id, "Uy vazifa baholandi",
                              f"{hw.title} — AI bahosi: {score}/5",
                              notification_type="homework")
            await db.commit()
        except Exception:                      # noqa: BLE001
            pass

    # ── Ustozga Telegram orqali xabar (baho tugmalari bilan) ────────────────
    lesson_title = (await db.execute(
        select(Lesson.title).where(Lesson.id == hw.lesson_id))).scalars().first() or "—"
    try:
        await hw_grader.notify_teacher(db, hw, sub, sub.student, lesson_title)
    except Exception:                          # noqa: BLE001
        pass

    return _sub(sub)


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


async def _assert_can_grade(sub, current_user, db: AsyncSession):
    """Baholay oladi: admin/superadmin yoki shu o'quvchining o'z ustozi.

    Ustozda `courses:update` ruxsati bo'lmasligi mumkin (u kurs kontentini
    tahrirlamaydi), lekin o'z o'quvchisining uy vazifasini baholashi shart.
    """
    role = str(getattr(current_user, "role", ""))
    if role in ("admin", "superadmin"):
        return
    hw = (await db.execute(select(LessonHomework)
                           .where(LessonHomework.id == sub.homework_id))).scalar_one_or_none()
    if hw:
        owner = await hw_grader.teacher_for_student(db, sub.student_id, hw.lesson_id)
        if owner and owner.id == current_user.id:
            return
    await check_permission("courses", "update", current_user, db)


@router.patch("/homework/submissions/{sub_id}")
async def grade_submission(
    sub_id: uuid.UUID,
    data: GradePayload,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    sub = (await db.execute(select(LessonHomeworkSubmission).where(LessonHomeworkSubmission.id == sub_id))).scalar_one_or_none()
    if not sub:
        raise HTTPException(404, "Submission topilmadi")
    await _assert_can_grade(sub, current_user, db)
    if data.score is not None:
        sub.score = data.score
    if data.feedback is not None:
        sub.feedback = data.feedback
    if data.status is not None:
        sub.status = data.status
    if data.score is not None or data.feedback is not None:
        # Ustoz qo'lda baholadi — AI bahosi ai_score da saqlanib qoladi
        sub.graded_by = current_user.id
        sub.graded_at = local_now()
        if data.status is None:
            sub.status = SubmissionStatus.graded
    await db.commit()

    if data.score is not None:
        try:
            hw = (await db.execute(select(LessonHomework)
                                   .where(LessonHomework.id == sub.homework_id))).scalar_one_or_none()
            await notify_user(db, sub.student_id, "Uy vazifa bahosi yangilandi",
                              f"{hw.title if hw else 'Uy vazifa'} — ustoz bahosi: {data.score}/5",
                              notification_type="homework")
            await db.commit()
        except Exception:                      # noqa: BLE001
            pass

    # `student` bog'lanishini oldindan yuklab qaytaramiz —
    # aks holda _sub() ichida lazy-load async kontekstda uzilib qoladi.
    fresh = (await db.execute(
        select(LessonHomeworkSubmission)
        .options(selectinload(LessonHomeworkSubmission.student))
        .where(LessonHomeworkSubmission.id == sub_id)
    )).scalar_one()
    return _sub(fresh)
