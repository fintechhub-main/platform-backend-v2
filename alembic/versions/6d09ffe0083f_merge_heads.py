"""merge_heads

Revision ID: 6d09ffe0083f
Revises: 372ed6e4c336, 959eccd04f81
Create Date: 2026-07-01 17:34:08.829120

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '6d09ffe0083f'
down_revision: Union[str, None] = ('372ed6e4c336', '959eccd04f81')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
