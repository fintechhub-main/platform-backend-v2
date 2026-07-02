import uuid
from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.lesson import Module, Lesson
from app.models.group_progress import GroupModuleAccess, GroupLessonDone
from app.dependencies import get_current_user, require_permission

router = APIRouter(prefix="/groups", tags=["group-progress"])


@router.get("/{group_id}/progress")
async def get_group_progress(
    group_id: uuid.UUID,
    course_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("groups", "view")),
):
    """Return modules with lessons + per-group open/done state."""
    modules = (await db.execute(
        select(Module)
        .options(selectinload(Module.lessons))
        .where(Module.course_id == course_id)
        .order_by(Module.order)
    )).scalars().all()

    # Open modules for this group
    open_q = (await db.execute(
        select(GroupModuleAccess.module_id)
        .where(GroupModuleAccess.group_id == group_id, GroupModuleAccess.is_open == True)
    )).scalars().all()
    open_modules = set(str(m) for m in open_q)

    # Lesson states for this group
    lesson_rows = (await db.execute(
        select(GroupLessonDone)
        .where(GroupLessonDone.group_id == group_id)
    )).scalars().all()
    lesson_state = {str(r.lesson_id): r for r in lesson_rows}

    result = []
    for mod in modules:
        lessons_out = []
        for les in mod.lessons:
            state = lesson_state.get(str(les.id))
            lessons_out.append({
                "id": str(les.id),
                "title": les.title,
                "type": les.type.value,
                "order": les.order,
                "duration": les.duration,
                "is_open": state.is_open if state else False,
                "is_done": state.is_done if state else False,
            })
        result.append({
            "id": str(mod.id),
            "title": mod.title,
            "order": mod.order,
            "is_open": str(mod.id) in open_modules,
            "lessons": lessons_out,
        })

    return result


@router.patch("/{group_id}/modules/{module_id}/access", dependencies=[Depends(require_permission("groups", "update"))])
async def set_module_access(
    group_id: uuid.UUID,
    module_id: uuid.UUID,
    is_open: bool = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Open or close a module for a group."""
    existing = (await db.execute(
        select(GroupModuleAccess)
        .where(GroupModuleAccess.group_id == group_id, GroupModuleAccess.module_id == module_id)
    )).scalar_one_or_none()

    if existing:
        existing.is_open = is_open
    else:
        db.add(GroupModuleAccess(group_id=group_id, module_id=module_id, is_open=is_open))

    await db.commit()
    return {"group_id": str(group_id), "module_id": str(module_id), "is_open": is_open}


@router.patch("/{group_id}/lessons/{lesson_id}/access", dependencies=[Depends(require_permission("groups", "update"))])
async def set_lesson_access(
    group_id: uuid.UUID,
    lesson_id: uuid.UUID,
    is_open: bool = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Open or close a lesson for a group."""
    existing = (await db.execute(
        select(GroupLessonDone)
        .where(GroupLessonDone.group_id == group_id, GroupLessonDone.lesson_id == lesson_id)
    )).scalar_one_or_none()

    if existing:
        existing.is_open = is_open
    else:
        db.add(GroupLessonDone(group_id=group_id, lesson_id=lesson_id, is_open=is_open, is_done=False))

    await db.commit()
    return {"group_id": str(group_id), "lesson_id": str(lesson_id), "is_open": is_open}


@router.patch("/{group_id}/lessons/{lesson_id}/done", dependencies=[Depends(require_permission("groups", "update"))])
async def set_lesson_done(
    group_id: uuid.UUID,
    lesson_id: uuid.UUID,
    is_done: bool = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Mark a lesson as done or undone for a group."""
    existing = (await db.execute(
        select(GroupLessonDone)
        .where(GroupLessonDone.group_id == group_id, GroupLessonDone.lesson_id == lesson_id)
    )).scalar_one_or_none()

    if existing:
        existing.is_done = is_done
    else:
        db.add(GroupLessonDone(group_id=group_id, lesson_id=lesson_id, is_open=False, is_done=is_done))

    await db.commit()
    return {"group_id": str(group_id), "lesson_id": str(lesson_id), "is_done": is_done}
