"""allow negative fantasy points

Revision ID: d3c7f8a91b24
Revises: c8d4f6a2b901
Create Date: 2026-10-27 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "d3c7f8a91b24"
down_revision: str | Sequence[str] | None = "c8d4f6a2b901"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


NON_NEGATIVE_STAT_CHECK = """
    kicks >= 0 AND
    marks >= 0 AND
    handballs >= 0 AND
    goals >= 0 AND
    behinds >= 0 AND
    hitouts >= 0 AND
    tackles >= 0 AND
    rebound_50s >= 0 AND
    inside_50s >= 0 AND
    clearances >= 0 AND
    clangers >= 0 AND
    free_kicks_for >= 0 AND
    free_kicks_against >= 0 AND
    contested_possessions >= 0 AND
    uncontested_possessions >= 0 AND
    contested_marks >= 0 AND
    marks_inside_50 >= 0 AND
    one_percenters >= 0 AND
    bounces >= 0 AND
    goal_assists >= 0
"""


def _replace_stat_check(condition: str) -> None:
    op.drop_constraint(
        "player_game_stats_check",
        "player_game_stats",
        type_="check",
    )
    op.create_check_constraint(
        "player_game_stats_check",
        "player_game_stats",
        condition,
    )


def upgrade() -> None:
    _replace_stat_check(NON_NEGATIVE_STAT_CHECK)


def downgrade() -> None:
    op.execute(
        "UPDATE player_game_stats SET fantasy_points = 0 " "WHERE fantasy_points < 0"
    )
    _replace_stat_check(NON_NEGATIVE_STAT_CHECK + " AND fantasy_points >= 0")
