"""use game for player stats identity

Revision ID: 4f2a6c89d2ef
Revises: 098560416458
Create Date: 2026-08-13 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "4f2a6c89d2ef"
down_revision: Union[str, Sequence[str], None] = "098560416458"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("player_game_stats_pkey", "player_game_stats", type_="primary")
    op.drop_constraint(
        "player_game_stats_player_id_game_id_key",
        "player_game_stats",
        type_="unique",
    )
    op.drop_column("player_game_stats", "player_game_number")
    op.create_primary_key(
        "player_game_stats_pkey",
        "player_game_stats",
        ["player_id", "game_id"],
    )


def downgrade() -> None:
    op.add_column(
        "player_game_stats",
        sa.Column("player_game_number", sa.Integer(), nullable=True),
    )
    op.execute(
        """
        WITH numbered_games AS (
            SELECT
                stats.player_id,
                stats.game_id,
                ROW_NUMBER() OVER (
                    PARTITION BY stats.player_id
                    ORDER BY game.start_date, stats.game_id
                ) AS player_game_number
            FROM player_game_stats AS stats
            JOIN game ON game.id = stats.game_id
        )
        UPDATE player_game_stats AS stats
        SET player_game_number = numbered_games.player_game_number
        FROM numbered_games
        WHERE stats.player_id = numbered_games.player_id
          AND stats.game_id = numbered_games.game_id
        """
    )
    op.alter_column("player_game_stats", "player_game_number", nullable=False)
    op.drop_constraint("player_game_stats_pkey", "player_game_stats", type_="primary")
    op.create_primary_key(
        "player_game_stats_pkey",
        "player_game_stats",
        ["player_id", "player_game_number"],
    )
    op.create_unique_constraint(
        "player_game_stats_player_id_game_id_key",
        "player_game_stats",
        ["player_id", "game_id"],
    )
