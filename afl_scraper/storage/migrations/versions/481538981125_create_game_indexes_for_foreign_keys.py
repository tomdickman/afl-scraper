"""create game indexes for foreign keys

Revision ID: 481538981125
Revises: 9fe22a591a68
Create Date: 2026-01-15 21:49:46.204156

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '481538981125'
down_revision: Union[str, Sequence[str], None] = '9fe22a591a68'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_game_venue",
        "game",
        ["venue"],
    )
    op.create_index(
        "ix_game_home_team",
        "game",
        ["home_team"],
    )
    op.create_index(
        "ix_game_away_team",
        "game",
        ["away_team"],
    )


def downgrade() -> None:
    op.drop_index("ix_game_venue", table_name="game")
    op.drop_index("ix_game_home_team", table_name="game")
    op.drop_index("ix_game_away_team", table_name="game")
