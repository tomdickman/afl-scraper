"""create venue table

Revision ID: f6ae240437b5
Revises: c6230ed6782e
Create Date: 2025-12-28 09:18:26.674021

"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f6ae240437b5"
down_revision: Union[str, Sequence[str], None] = "c6230ed6782e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    sql = Path("afl_scraper/storage/tables/venue.sql").read_text()

    op.execute(sql)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS venue;")
