"""add branch_id to courses

Revision ID: 1f3920ac6c56
Revises: 117206b64311
Create Date: 2026-06-29 18:27:12.849734

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '1f3920ac6c56'
down_revision: Union[str, None] = '117206b64311'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('courses', sa.Column('branch_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_courses_branch_id', 'courses', 'branches', ['branch_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint('fk_courses_branch_id', 'courses', type_='foreignkey')
    op.drop_column('courses', 'branch_id')
