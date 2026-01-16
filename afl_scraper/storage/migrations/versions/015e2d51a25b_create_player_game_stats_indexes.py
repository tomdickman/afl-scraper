"""create player game stats indexes

Revision ID: 015e2d51a25b
Revises: 481538981125
Create Date: 2026-01-16 21:55:45.105990

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "015e2d51a25b"
down_revision: Union[str, Sequence[str], None] = "481538981125"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_player_game_stats_game",
        "player_game_stats",
        ["game_id"],
    )
    op.create_index(
        "ix_player_game_stats_game_player",
        "player_game_stats",
        ["game_id", "player_id"],
    )
    op.create_index(
        "ix_player_game_stats_team",
        "player_game_stats",
        ["team"],
    )


def downgrade() -> None:
    op.drop_index("ix_player_game_stats_game_player", table_name="player_game_stats")
    op.drop_index("ix_player_game_stats_game", table_name="player_game_stats")
    op.drop_index("ix_player_game_stats_team", table_name="player_game_stats")
