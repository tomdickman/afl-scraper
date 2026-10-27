"""correct grouped elimination finals

Revision ID: c51e0f33a219
Revises: a37bd1fd30ec
Create Date: 2026-10-27 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "c51e0f33a219"
down_revision: str | Sequence[str] | None = "a37bd1fd30ec"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# AFL Official grouped these individual games under a combined first-finals-week
# label. AFL Tables and AustralianFootball independently agree that these are
# elimination finals. Source-qualified identities make the repair deterministic
# without guessing from game order, winner, or date.
_ELIMINATION_FINAL_MATCH_IDS = (
    "224",
    "225",
    "479",
    "486",
    "704",
    "709",
    "938",
    "945",
    "1147",
    "1153",
    "1435",
    "1437",
    "1698",
    "1703",
    "1949",
    "1952",
    "2896",
    "2897",
    "3732",
    "3733",
    "4740",
    "4743",
    "5840",
    "5841",
    "6914",
    "6915",
    "8004",
    "8005",
    "9022",
    "9025",
)


def _set_round(round_: str) -> None:
    quoted_ids = ", ".join(f"'{match_id}'" for match_id in _ELIMINATION_FINAL_MATCH_IDS)
    op.execute(
        f"""
        UPDATE game AS game
        SET round = '{round_}'
        FROM game_source_identity AS identity
        WHERE identity.game_id = game.id
          AND identity.source = 'afl_official'
          AND identity.source_match_id IN ({quoted_ids})
        """
    )


def upgrade() -> None:
    _set_round("EF")


def downgrade() -> None:
    # Restore the preceding migration's combined-group classification.
    _set_round("QF")
