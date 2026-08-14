"""allow unavailable player stats

Revision ID: 7d1d45f2a3c8
Revises: 81ca20df131b
Create Date: 2026-08-15 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "7d1d45f2a3c8"
down_revision: Union[str, Sequence[str], None] = "81ca20df131b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OPTIONAL_STAT_COLUMNS = (
    "rebound_50s",
    "inside_50s",
    "clangers",
    "free_kicks_for",
    "free_kicks_against",
    "contested_possessions",
    "uncontested_possessions",
    "contested_marks",
    "marks_inside_50",
    "one_percenters",
    "bounces",
)


def upgrade() -> None:
    for column in OPTIONAL_STAT_COLUMNS:
        op.alter_column(
            "player_game_stats",
            column,
            existing_type=sa.Integer(),
            nullable=True,
        )


def downgrade() -> None:
    for column in OPTIONAL_STAT_COLUMNS:
        op.execute(
            sa.text(
                f'UPDATE player_game_stats SET "{column}" = 0 '
                f'WHERE "{column}" IS NULL'
            )
        )
        op.alter_column(
            "player_game_stats",
            column,
            existing_type=sa.Integer(),
            nullable=False,
        )
