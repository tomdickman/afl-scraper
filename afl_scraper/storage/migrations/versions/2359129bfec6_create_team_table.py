"""create team table

Revision ID: 2359129bfec6
Revises: f6ae240437b5
Create Date: 2025-12-28 09:25:53.445215

"""

from collections.abc import Sequence
from pathlib import Path

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2359129bfec6"
down_revision: str | Sequence[str] | None = "f6ae240437b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    sql = Path("afl_scraper/storage/tables/team.sql").read_text()

    op.execute(sql)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS team;")
