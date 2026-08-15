"""add source-qualified identities for historical loading

Revision ID: b6df0c4a1e92
Revises: 7d1d45f2a3c8
Create Date: 2026-08-16 00:00:00.000000

"""

from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b6df0c4a1e92"
down_revision: Union[str, Sequence[str], None] = "7d1d45f2a3c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


HISTORICALLY_UNAVAILABLE_STATS = (
    "clearances",
    "goal_assists",
    "time_on_ground_percent",
    "fantasy_points",
)


def upgrade() -> None:
    op.execute(
        Path("afl_scraper/storage/tables/player_source_identity.sql").read_text()
    )
    op.execute(Path("afl_scraper/storage/tables/game_source_identity.sql").read_text())
    op.execute(
        """
        INSERT INTO player_source_identity
          (source, source_player_id, year, player_id)
        SELECT 'afl_official', afl_official_id, year, player_id
        FROM player_id_mapping
        WHERE afl_official_id IS NOT NULL
        """
    )
    op.execute(
        """
        INSERT INTO game_source_identity (source, source_match_id, game_id)
        SELECT 'afl_official', id::text, id FROM game
        """
    )
    op.execute("CREATE SEQUENCE game_internal_id_seq")
    op.execute(
        """
        SELECT setval(
          'game_internal_id_seq',
          GREATEST(COALESCE((SELECT MAX(id) FROM game), 0), 1),
          COALESCE((SELECT MAX(id) FROM game), 0) > 0
        )
        """
    )
    op.execute("DROP TABLE player_id_mapping")

    for column in HISTORICALLY_UNAVAILABLE_STATS:
        column_type = (
            sa.Numeric(5, 2) if column == "time_on_ground_percent" else sa.Integer()
        )
        op.alter_column(
            "player_game_stats",
            column,
            existing_type=column_type,
            nullable=True,
        )


def downgrade() -> None:
    for column in HISTORICALLY_UNAVAILABLE_STATS:
        column_type = (
            sa.Numeric(5, 2) if column == "time_on_ground_percent" else sa.Integer()
        )
        op.execute(
            sa.text(
                f'UPDATE player_game_stats SET "{column}" = 0 '
                f'WHERE "{column}" IS NULL'
            )
        )
        op.alter_column(
            "player_game_stats",
            column,
            existing_type=column_type,
            nullable=False,
        )

    op.execute(Path("afl_scraper/storage/tables/player_id_mapping.sql").read_text())
    op.execute(
        """
        INSERT INTO player_id_mapping
          (afl_official_id, player_id, year)
        SELECT source_player_id, player_id, year
        FROM player_source_identity
        WHERE source = 'afl_official'
        """
    )
    op.execute("DROP TABLE game_source_identity")
    op.execute("DROP TABLE player_source_identity")
    op.execute("DROP SEQUENCE game_internal_id_seq")
