"""create player_id_mapping table

Revision ID: 098560416458
Revises: 7a5e553d0f10_add_barossa_park_venue
Create Date: 2026-04-28 10:30:00.000000

"""

from collections.abc import Sequence
from pathlib import Path

from alembic import op

revision: str = "098560416458"
down_revision: str | Sequence[str] | None = "7a5e553d0f10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    sql = Path("afl_scraper/storage/tables/player_id_mapping.sql").read_text()
    op.execute(sql)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS player_id_mapping;")
