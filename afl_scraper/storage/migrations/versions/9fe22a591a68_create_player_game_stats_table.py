"""create player game stats table

Revision ID: 9fe22a591a68
Revises: 08e056499bbd
Create Date: 2026-01-12 21:22:58.578840

"""

from typing import Sequence, Union
from pathlib import Path

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9fe22a591a68"
down_revision: Union[str, Sequence[str], None] = "08e056499bbd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Historical migrations must use an immutable schema snapshot. Reading the
    # current table definition here would make a fresh migration chain skip the
    # legacy shape expected by later migrations.
    sql = Path("afl_scraper/storage/tables/player_game_stats_v1.sql").read_text()

    op.execute(sql)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS player_game_stats;")
