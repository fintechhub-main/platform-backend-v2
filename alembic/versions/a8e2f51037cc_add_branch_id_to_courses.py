"""add branch_id to courses

Revision ID: a8e2f51037cc
Revises: 1f3920ac6c56
Create Date: 2026-06-29 18:29:12.184760

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a8e2f51037cc'
down_revision: Union[str, None] = '1f3920ac6c56'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
