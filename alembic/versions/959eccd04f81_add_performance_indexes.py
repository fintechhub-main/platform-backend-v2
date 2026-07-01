"""add_performance_indexes

Revision ID: 959eccd04f81
Revises: 117206b64311
Create Date: 2026-06-30 17:11:55.993229

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '959eccd04f81'
down_revision: Union[str, None] = '117206b64311'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('ix_attendance_date', 'attendance', ['date'], unique=False)
    op.create_index('ix_attendance_group_id', 'attendance', ['group_id'], unique=False)
    op.create_index('ix_attendance_student_id', 'attendance', ['student_id'], unique=False)
    op.create_index('ix_attendance_student_group_date', 'attendance', ['student_id', 'group_id', 'date'], unique=False)
    op.create_index('ix_group_students_group_id', 'group_students', ['group_id'], unique=False)
    op.create_index('ix_group_students_student_id', 'group_students', ['student_id'], unique=False)
    op.create_index('ix_groups_branch_id', 'groups', ['branch_id'], unique=False)
    op.create_index('ix_groups_course_id', 'groups', ['course_id'], unique=False)
    op.create_index('ix_groups_teacher_id', 'groups', ['teacher_id'], unique=False)
    op.create_index('ix_users_branch_id', 'users', ['branch_id'], unique=False)
    op.create_index('ix_users_role', 'users', ['role'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_users_role', table_name='users')
    op.drop_index('ix_users_branch_id', table_name='users')
    op.drop_index('ix_groups_teacher_id', table_name='groups')
    op.drop_index('ix_groups_course_id', table_name='groups')
    op.drop_index('ix_groups_branch_id', table_name='groups')
    op.drop_index('ix_group_students_student_id', table_name='group_students')
    op.drop_index('ix_group_students_group_id', table_name='group_students')
    op.drop_index('ix_attendance_student_group_date', table_name='attendance')
    op.drop_index('ix_attendance_student_id', table_name='attendance')
    op.drop_index('ix_attendance_group_id', table_name='attendance')
    op.drop_index('ix_attendance_date', table_name='attendance')
