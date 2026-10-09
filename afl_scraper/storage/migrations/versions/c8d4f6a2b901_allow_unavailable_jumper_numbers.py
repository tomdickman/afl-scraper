"""allow unavailable jumper numbers

Revision ID: c8d4f6a2b901
Revises: a4d9c2e71b30
Create Date: 2026-10-10 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8d4f6a2b901"
down_revision: str | Sequence[str] | None = "a4d9c2e71b30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "player_game_stats",
        "jumper_number",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            'UPDATE player_game_stats SET "jumper_number" = 0 '
            'WHERE "jumper_number" IS NULL'
        )
    )
    op.alter_column(
        "player_game_stats",
        "jumper_number",
        existing_type=sa.Integer(),
        nullable=False,
    )
