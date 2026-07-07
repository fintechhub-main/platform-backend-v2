import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.models.group_project import GroupProject, GroupProjectTask, TaskComment
from app.models.user import User

router = APIRouter(prefix="/group-projects", tags=["group-projects"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    title: str
    description: Optional[str] = None
    teacher_id: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    project_url: Optional[str] = None
    figma_url: Optional[str] = None
    github_repos: Optional[dict] = None
    student_ids: Optional[List[str]] = None


class ProjectUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    teacher_id: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    project_url: Optional[str] = None
    figma_url: Optional[str] = None
    github_repos: Optional[dict] = None
    student_ids: Optional[List[str]] = None


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    direction: Optional[str] = None
    status: str = "planned"
    deadline: Optional[str] = None
    student_ids: Optional[List[str]] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    direction: Optional[str] = None
    status: Optional[str] = None
    deadline: Optional[str] = None
    student_ids: Optional[List[str]] = None


class CommentCreate(BaseModel):
    comment: str


# ── Helpers ──────────────────────────────────────────────────────────────────

def _user_mini(u: User):
    return {"id": str(u.id), "full_name": u.full_name, "role": str(u.role)}


def _task_out(t: GroupProjectTask):
    return {
        "id": str(t.id),
        "project_id": str(t.project_id),
        "title": t.title,
        "description": t.description,
        "direction": t.direction,
        "status": t.status,
        "deadline": str(t.deadline) if t.deadline else None,
        "created_at": t.created_at.isoformat(),
        "students": [_user_mini(u) for u in (t.students or [])],
        "comments": [
            {
                "id": str(c.id),
                "comment": c.comment,
                "user": _user_mini(c.user) if c.user else None,
                "created_at": c.created_at.isoformat(),
            }
            for c in (t.comments or [])
        ],
    }


def _project_out(p: GroupProject):
    return {
        "id": str(p.id),
        "title": p.title,
        "description": p.description,
        "teacher": _user_mini(p.teacher) if p.teacher else None,
        "start_date": str(p.start_date) if p.start_date else None,
        "end_date": str(p.end_date) if p.end_date else None,
        "project_url": p.project_url,
        "figma_url": p.figma_url,
        "github_repos": p.github_repos or {},
        "created_at": p.created_at.isoformat(),
        "students": [_user_mini(u) for u in (p.students or [])],
        "tasks": [_task_out(t) for t in (p.tasks or [])],
    }


async def _load_project(project_id: uuid.UUID, db: AsyncSession) -> GroupProject:
    result = await db.execute(
        select(GroupProject)
        .options(
            selectinload(GroupProject.teacher),
            selectinload(GroupProject.students),
            selectinload(GroupProject.tasks)
            .selectinload(GroupProjectTask.students),
            selectinload(GroupProject.tasks)
            .selectinload(GroupProjectTask.comments)
            .selectinload(TaskComment.user),
        )
        .where(GroupProject.id == project_id)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Loyiha topilmadi")
    return p


# ── Projects ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_projects(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from datetime import date
    q = (
        select(GroupProject)
        .options(
            selectinload(GroupProject.teacher),
            selectinload(GroupProject.students),
            selectinload(GroupProject.tasks).selectinload(GroupProjectTask.students),
            selectinload(GroupProject.tasks).selectinload(GroupProjectTask.comments).selectinload(TaskComment.user),
        )
        .order_by(GroupProject.created_at.desc())
        .offset(skip).limit(limit)
    )
    role = str(getattr(current_user, "role", ""))
    if role == "student":
        # filter projects that include this student
        from app.models.group_project import group_project_students
        from sqlalchemy import exists
        sub = (
            select(group_project_students.c.project_id)
            .where(group_project_students.c.user_id == current_user.id)
            .scalar_subquery()
        )
        q = q.where(GroupProject.id.in_(sub))
    result = await db.execute(q)
    return [_project_out(p) for p in result.scalars().all()]


@router.post("", status_code=201)
async def create_project(
    data: ProjectCreate,
    _=Depends(require_permission("settings", "create")),
    db: AsyncSession = Depends(get_db),
):
    from datetime import date
    proj = GroupProject(
        title=data.title,
        description=data.description,
        teacher_id=uuid.UUID(data.teacher_id) if data.teacher_id else None,
        project_url=data.project_url,
        figma_url=data.figma_url,
        github_repos=data.github_repos or {},
    )
    if data.start_date:
        proj.start_date = date.fromisoformat(data.start_date)
    if data.end_date:
        proj.end_date = date.fromisoformat(data.end_date)
    db.add(proj)
    await db.flush()

    if data.student_ids:
        students_res = await db.execute(
            select(User).where(User.id.in_([uuid.UUID(s) for s in data.student_ids]))
        )
        proj.students = list(students_res.scalars().all())

    await db.commit()
    return _project_out(await _load_project(proj.id, db))


@router.get("/{project_id}")
async def get_project(
    project_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return _project_out(await _load_project(project_id, db))


@router.patch("/{project_id}")
async def update_project(
    project_id: uuid.UUID,
    data: ProjectUpdate,
    _=Depends(require_permission("settings", "update")),
    db: AsyncSession = Depends(get_db),
):
    from datetime import date
    result = await db.execute(select(GroupProject).where(GroupProject.id == project_id))
    proj = result.scalar_one_or_none()
    if not proj:
        raise HTTPException(404, "Loyiha topilmadi")

    updates = data.model_dump(exclude_unset=True)
    student_ids = updates.pop("student_ids", None)
    if "start_date" in updates and updates["start_date"]:
        proj.start_date = date.fromisoformat(updates.pop("start_date"))
    if "end_date" in updates and updates["end_date"]:
        proj.end_date = date.fromisoformat(updates.pop("end_date"))
    if "teacher_id" in updates:
        proj.teacher_id = uuid.UUID(updates.pop("teacher_id")) if updates["teacher_id"] else None

    for k, v in updates.items():
        setattr(proj, k, v)

    if student_ids is not None:
        students_res = await db.execute(
            select(User).where(User.id.in_([uuid.UUID(s) for s in student_ids]))
        )
        proj.students = list(students_res.scalars().all())

    await db.commit()
    return _project_out(await _load_project(project_id, db))


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: uuid.UUID,
    _=Depends(require_permission("settings", "delete")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(GroupProject).where(GroupProject.id == project_id))
    proj = result.scalar_one_or_none()
    if not proj:
        raise HTTPException(404, "Loyiha topilmadi")
    await db.delete(proj)
    await db.commit()


# ── Tasks ─────────────────────────────────────────────────────────────────────

@router.post("/{project_id}/tasks", status_code=201)
async def create_task(
    project_id: uuid.UUID,
    data: TaskCreate,
    _=Depends(require_permission("settings", "create")),
    db: AsyncSession = Depends(get_db),
):
    from datetime import date
    result = await db.execute(select(GroupProject).where(GroupProject.id == project_id))
    if not result.scalar_one_or_none():
        raise HTTPException(404, "Loyiha topilmadi")

    task = GroupProjectTask(
        project_id=project_id,
        title=data.title,
        description=data.description,
        direction=data.direction,
        status=data.status,
    )
    if data.deadline:
        task.deadline = date.fromisoformat(data.deadline)
    db.add(task)
    await db.flush()

    if data.student_ids:
        students_res = await db.execute(
            select(User).where(User.id.in_([uuid.UUID(s) for s in data.student_ids]))
        )
        task.students = list(students_res.scalars().all())

    await db.commit()
    await db.refresh(task)

    task_result = await db.execute(
        select(GroupProjectTask)
        .options(selectinload(GroupProjectTask.students), selectinload(GroupProjectTask.comments).selectinload(TaskComment.user))
        .where(GroupProjectTask.id == task.id)
    )
    return _task_out(task_result.scalar_one())


@router.patch("/{project_id}/tasks/{task_id}")
async def update_task(
    project_id: uuid.UUID,
    task_id: uuid.UUID,
    data: TaskUpdate,
    _=Depends(require_permission("settings", "update")),
    db: AsyncSession = Depends(get_db),
):
    from datetime import date
    result = await db.execute(
        select(GroupProjectTask)
        .options(selectinload(GroupProjectTask.students), selectinload(GroupProjectTask.comments).selectinload(TaskComment.user))
        .where(GroupProjectTask.id == task_id, GroupProjectTask.project_id == project_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Vazifa topilmadi")

    updates = data.model_dump(exclude_unset=True)
    student_ids = updates.pop("student_ids", None)
    if "deadline" in updates and updates["deadline"]:
        task.deadline = date.fromisoformat(updates.pop("deadline"))
    for k, v in updates.items():
        setattr(task, k, v)
    if student_ids is not None:
        students_res = await db.execute(
            select(User).where(User.id.in_([uuid.UUID(s) for s in student_ids]))
        )
        task.students = list(students_res.scalars().all())

    await db.commit()
    await db.refresh(task)
    return _task_out(task)


@router.delete("/{project_id}/tasks/{task_id}", status_code=204)
async def delete_task(
    project_id: uuid.UUID,
    task_id: uuid.UUID,
    _=Depends(require_permission("settings", "delete")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(GroupProjectTask)
        .where(GroupProjectTask.id == task_id, GroupProjectTask.project_id == project_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Vazifa topilmadi")
    await db.delete(task)
    await db.commit()


# ── Task Comments ─────────────────────────────────────────────────────────────

@router.post("/{project_id}/tasks/{task_id}/comments", status_code=201)
async def add_comment(
    project_id: uuid.UUID,
    task_id: uuid.UUID,
    data: CommentCreate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(GroupProjectTask)
        .where(GroupProjectTask.id == task_id, GroupProjectTask.project_id == project_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(404, "Vazifa topilmadi")

    comment = TaskComment(task_id=task_id, user_id=current_user.id, comment=data.comment)
    db.add(comment)
    await db.commit()
    await db.refresh(comment)

    user_result = await db.execute(select(User).where(User.id == comment.user_id))
    comment.user = user_result.scalar_one_or_none()
    return {
        "id": str(comment.id),
        "task_id": str(comment.task_id),
        "comment": comment.comment,
        "user": _user_mini(comment.user) if comment.user else None,
        "created_at": comment.created_at.isoformat(),
    }


@router.delete("/{project_id}/tasks/{task_id}/comments/{comment_id}", status_code=204)
async def delete_comment(
    project_id: uuid.UUID,
    task_id: uuid.UUID,
    comment_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(TaskComment).where(TaskComment.id == comment_id))
    comment = result.scalar_one_or_none()
    if not comment:
        raise HTTPException(404, "Izoh topilmadi")
    role = str(getattr(current_user, "role", ""))
    if role not in {"admin", "superadmin"} and comment.user_id != current_user.id:
        raise HTTPException(403, "Ruxsat yo'q")
    await db.delete(comment)
    await db.commit()
