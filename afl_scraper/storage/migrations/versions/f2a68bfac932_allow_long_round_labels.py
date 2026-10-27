"""allow long round labels

Revision ID: f2a68bfac932
Revises: d3c7f8a91b24
Create Date: 2026-10-27 00:00:00.000000

"""

from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision: str = "f2a68bfac932"
down_revision: str | Sequence[str] | None = "d3c7f8a91b24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _drop_career_game_view() -> None:
    op.execute("DROP VIEW IF EXISTS player_game_stats_with_career_number")


def _create_career_game_view() -> None:
    sql = Path(
        "afl_scraper/storage/tables/player_game_stats_with_career_number.sql"
    ).read_text()
    op.execute(sql)


def _require_rounds_fit_legacy_column() -> None:
    rows = (
        op.get_bind()
        .execute(
            sa.text(
                """
            SELECT id, CHAR_LENGTH(round)
            FROM game
            WHERE CHAR_LENGTH(round) > 20
            ORDER BY id
            LIMIT 5
            """
            )
        )
        .fetchall()
    )
    if rows:
        sample = ", ".join(
            f"game {game_id} ({length} chars)" for game_id, length in rows
        )
        raise RuntimeError(
            "Cannot downgrade game.round to VARCHAR(20) while longer values "
            f"remain; normalize or shorten them first. Examples: {sample}"
        )


def upgrade() -> None:
    _drop_career_game_view()
    op.alter_column(
        "game",
        "round",
        existing_type=sa.String(length=20),
        type_=sa.Text(),
        existing_nullable=False,
    )
    _create_career_game_view()


def downgrade() -> None:
    _require_rounds_fit_legacy_column()
    _drop_career_game_view()
    op.alter_column(
        "game",
        "round",
        existing_type=sa.Text(),
        type_=sa.String(length=20),
        existing_nullable=False,
    )
    _create_career_game_view()
