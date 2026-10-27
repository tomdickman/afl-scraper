"""merge QE into QF

Revision ID: a37bd1fd30ec
Revises: 6d2f319ec61a
Create Date: 2026-10-27 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "a37bd1fd30ec"
down_revision: str | Sequence[str] | None = "6d2f319ec61a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("game_round_format", "game", type_="check")
    op.execute("UPDATE game SET round = 'QF' WHERE round = 'QE'")
    op.create_check_constraint(
        "game_round_format",
        "game",
        "round ~ '^([1-9][0-9]*|OR|WF|QF|EF|SF|PF|GF)$'",
    )


def downgrade() -> None:
    # QF does not retain whether its source grouped qualifying and elimination
    # finals, so the original QE rows cannot be identified without inventing
    # data. Retain QF values while restoring the preceding allowed-value set.
    op.drop_constraint("game_round_format", "game", type_="check")
    op.create_check_constraint(
        "game_round_format",
        "game",
        "round ~ '^([1-9][0-9]*|OR|WF|QE|QF|EF|SF|PF|GF)$'",
    )
