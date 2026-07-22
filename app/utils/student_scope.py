"""O'quvchiga ochiq darslarni aniqlash — bitta joyda.

Dars o'quvchi uchun ochiq deb hisoblanadi, agar:
  1. dars o'quvchi o'qiyotgan guruhlarning kursiga tegishli bo'lsa, VA
  2. dars global ochiq (`lessons.is_open`) yoki
     shu guruh uchun ochilgan (`group_lesson_done.is_open`) bo'lsa.

Birinchi shart muhim: usiz boshqa kurslardagi ochiq darslar va ularning
uy vazifalari ham o'quvchiga ko'rinib qolardi.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.group import Group, GroupStudent
from app.models.group_progress import GroupLessonDone
from app.models.lesson import Lesson, Module


async def my_course_ids(db: AsyncSession, student_id) -> set:
    rows = (await db.execute(
        select(Group.course_id)
        .join(GroupStudent, GroupStudent.group_id == Group.id)
        .where(GroupStudent.student_id == student_id)
    )).scalars().all()
    return {c for c in rows if c}


async def open_lesson_ids(db: AsyncSession, student_id) -> set:
    """O'quvchiga ochiq darslar id lari."""
    course_ids = await my_course_ids(db, student_id)
    if not course_ids:
        return set()

    # o'z kurslaridagi global ochiq darslar
    globally = (await db.execute(
        select(Lesson.id)
        .join(Module, Module.id == Lesson.module_id)
        .where(Module.course_id.in_(course_ids), Lesson.is_open == True)  # noqa: E712
    )).scalars().all()

    # guruhi uchun maxsus ochilgan darslar
    per_group = (await db.execute(
        select(GroupLessonDone.lesson_id)
        .join(GroupStudent, GroupStudent.group_id == GroupLessonDone.group_id)
        .where(GroupStudent.student_id == student_id,
               GroupLessonDone.is_open == True)  # noqa: E712
    )).scalars().all()

    return {*globally, *per_group}
