"""create player career game view

Revision ID: 81ca20df131b
Revises: 4f2a6c89d2ef
Create Date: 2026-08-14 00:00:00.000000

"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "81ca20df131b"
down_revision: Union[str, Sequence[str], None] = "4f2a6c89d2ef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    sql = Path(
        "afl_scraper/storage/tables/player_game_stats_with_career_number.sql"
    ).read_text()
    op.execute(sql)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS player_game_stats_with_career_number;")
