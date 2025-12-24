"""create player table

Revision ID: c6230ed6782e
Revises:
Create Date: 2025-12-24 15:39:46.447009

"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c6230ed6782e"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    sql = Path("afl_scraper/storage/tables/player.sql").read_text()

    op.execute(sql)


def downgrade():
    op.execute("DROP TABLE IF EXISTS player;")
