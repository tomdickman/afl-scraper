"""create game table

Revision ID: 08e056499bbd
Revises: 2359129bfec6
Create Date: 2025-12-29 22:22:59.495235

"""
from pathlib import Path
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '08e056499bbd'
down_revision: Union[str, Sequence[str], None] = '2359129bfec6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    sql = Path("afl_scraper/storage/tables/game.sql").read_text()

    op.execute(sql)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS game;")
