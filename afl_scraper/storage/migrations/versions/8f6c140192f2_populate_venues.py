"""populate venues

Revision ID: 8f6c140192f2
Revises: 015e2d51a25b
Create Date: 2026-01-23 21:57:34.282530

"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "8f6c140192f2"
down_revision: Union[str, Sequence[str], None] = "015e2d51a25b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    sql_path = Path(__file__).parents[2] / "data/init_venues.sql"
    sql = sql_path.resolve().read_text()

    op.execute(sql)


def downgrade() -> None:
    op.execute("TRUNCATE TABLE venue RESTART IDENTITY CASCADE")
