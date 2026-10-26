"""normalize game rounds

Revision ID: 6d2f319ec61a
Revises: f2a68bfac932
Create Date: 2026-10-27 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "6d2f319ec61a"
down_revision: str | Sequence[str] | None = "f2a68bfac932"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE game
        SET round = CASE
          WHEN BTRIM(round) ~* '^round[[:space:]]+[0-9]+$'
            THEN (REGEXP_MATCH(
              BTRIM(round), '([0-9]+)$', 'i'
            ))[1]::INTEGER::TEXT
          WHEN BTRIM(round) ~ '^[0-9]+$'
            THEN BTRIM(round)::INTEGER::TEXT
          WHEN LOWER(BTRIM(round)) IN ('or', 'opening round') THEN 'OR'
          WHEN LOWER(BTRIM(round)) IN (
            'wf', 'wcf', 'wildcard final', 'wildcard finals'
          ) THEN 'WF'
          WHEN LOWER(BTRIM(round)) IN (
            'qe', 'fw1', 'finals week 1',
            'qualifying & elimination final',
            'qualifying & elimination finals'
          ) THEN 'QE'
          WHEN LOWER(BTRIM(round)) IN (
            'qf', 'qualifying final', 'qualifying finals'
          ) THEN 'QF'
          WHEN LOWER(BTRIM(round)) IN (
            'ef', 'elimination final', 'elimination finals'
          ) THEN 'EF'
          WHEN LOWER(BTRIM(round)) IN (
            'sf', 'fw2', 'finals week 2', 'semi final', 'semi finals'
          ) THEN 'SF'
          WHEN LOWER(BTRIM(round)) IN (
            'pf', 'fw3', 'finals week 3',
            'preliminary final', 'preliminary finals'
          ) THEN 'PF'
          WHEN LOWER(BTRIM(round)) IN (
            'gf', 'gfr', 'fw4', 'finals week 4',
            'grand final', 'grand finals', 'grand final replay'
          ) THEN 'GF'
          WHEN LOWER(BTRIM(round)) ~ '^[12](qf|ef|sf|pf)$'
            THEN UPPER(SUBSTRING(BTRIM(round) FROM 2))
          ELSE round
        END
        """
    )
    op.execute("ALTER TABLE game DROP CONSTRAINT IF EXISTS game_round_format")
    op.create_check_constraint(
        "game_round_format",
        "game",
        "round ~ '^([1-9][0-9]*|OR|WF|QE|QF|EF|SF|PF|GF)$'",
    )


def downgrade() -> None:
    # Canonical labels cannot be expanded back to their exact provider-native
    # spellings. Retain the losslessly usable canonical values while removing
    # the database constraint introduced by this revision.
    op.drop_constraint("game_round_format", "game", type_="check")
